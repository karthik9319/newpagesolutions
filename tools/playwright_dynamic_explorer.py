# tools/playwright_dynamic_explorer.py
"""
Playwright dynamic explorer (selector-free).
- Instruments page to log pointerover/mouseenter events.
- Injects a MutationObserver to capture DOM changes.
- Moves the mouse across the viewport using a human-like exploration policy
  (grid + random walks + targeted micro-probes).
- Aggregates discoveries (hover targets -> revealed nodes / links / popups).
- Produces structured JSON and a simple Gherkin generator for two scenarios:
    1) popup/overlay validation (if found)
    2) hover-based interaction validation (highest confidence)
"""

from playwright.sync_api import sync_playwright, Page
import time, math, random, json, traceback, html, re
from collections import defaultdict, Counter
from typing import Dict, Any, List, Optional


class PlaywrightDynamicExplorer:
    name = "playwright_dynamic_explorer"
    description = "Autonomously discover hover interactions without hardcoded selectors."

    def __init__(self, headless=True, viewport={"width": 1280, "height": 800}, probe_duration=6.0):
        """
        probe_duration: total seconds to spend exploring (approx)
        """
        self.headless = headless
        self.viewport = viewport
        self.probe_duration = probe_duration

    # -------------------------
    # Public run entry
    # -------------------------
    def run(self, url: str, click_verify: bool = False, click_timeout: float = 3.0) -> Dict[str, Any]:
        """
        url: page to explore
        click_verify: if True, will safely open revealed links in a new context to verify redirect
        """
        result = {
            "url": url,
            "hover_discoveries": [],
            "popup_discoveries": [],
            "errors": []
        }
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(viewport=self.viewport)
            page = context.new_page()

            # attach event listeners & mutation observer inside page
            try:
                page.goto(url, wait_until="networkidle", timeout=60000)
            except Exception as e:
                result["errors"].append(f"Navigation error: {e}")
                context.close()
                browser.close()
                return result

            # install instrumentation
            self._install_instrumentation(page)

            # also listen to Playwright-level dialog/popup events
            popup_pages = []

            def on_popup(p):
                popup_pages.append(p)

            page.on("popup", on_popup)

            dialogs = []

            def on_dialog(dialog):
                dialogs.append({
                    "type": dialog.type,
                    "message": dialog.message,
                    "defaultValue": getattr(dialog, "defaultValue", None)
                })
                try:
                    dialog.dismiss()
                except Exception:
                    pass

            page.on("dialog", on_dialog)

            # exploration policy: grid + random walk + micro-probes
            try:
                self._explore_page(page, total_time=self.probe_duration)
            except Exception as e:
                result["errors"].append(f"Exploration error: {e}\n{traceback.format_exc()}")

            # collect instrumentation logs
            try:
                events = page.evaluate("() => window.__hover_events || []")
            except Exception:
                events = []

            try:
                mutations = page.evaluate("() => window.__dom_mutations || []")
            except Exception:
                mutations = []

            # cluster events by element fingerprint (we compute an XPath-like descriptor in page)
            discoveries = self._aggregate_events(page, events, mutations)

            # detect popups and enrich
            popups = self._detect_popups(page, dialogs, popup_pages)

            result["hover_discoveries"] = discoveries
            result["popup_discoveries"] = popups

            # optional click verification for revealed links (safe: open in new context)
            if click_verify:
                try:
                    self._safe_click_verify(browser, discoveries, result, timeout=click_timeout)
                except Exception as e:
                    result["errors"].append(f"Click verify error: {e}\n{traceback.format_exc()}")

            # generate Gherkin (two scenarios)
            gherkin_text = self._generate_gherkin(result)
            result["generated_feature"] = gherkin_text

            context.close()
            browser.close()
            return result

    # -------------------------
    # Page instrumentation
    # -------------------------
    def _install_instrumentation(self, page: Page):
        """
        Injects:
          - global array window.__hover_events capturing pointerover/mouseenter with element fingerprint
          - MutationObserver storing added/removed nodes (outerHTML snippet)
        """
        install_script = r"""
        if (!window.__hover_events) {
            window.__hover_events = [];
        }
        if (!window.__dom_mutations) {
            window.__dom_mutations = [];
        }
        (function(){
            // utility: get compact fingerprint and XPath-like path
            function fingerprint(el) {
                if (!el || el.nodeType !== 1) return null;
                // small outerText/label
                let txt = (el.innerText || el.textContent || "").trim().replace(/\s+/g, " ").slice(0,200);
                // tag + classes + small index among siblings
                let tag = el.tagName.toLowerCase();
                let cls = (el.className || "").toString().split(/\s+/).filter(Boolean).slice(0,3).join('.');
                let idx = 1;
                let sib = el;
                while (sib.previousElementSibling) { idx++; sib = sib.previousElementSibling; }
                // bounding rect
                let r = el.getBoundingClientRect();
                let bbox = {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
                return {tag, cls, idx, txt, bbox};
            }

            // pointerover and mouseenter are both useful; store both
            document.addEventListener('pointerover', function(ev) {
                try {
                    const el = ev.target;
                    const fp = fingerprint(el);
                    window.__hover_events.push({type:'pointerover', time: Date.now(), target: fp});
                } catch(e){}
            }, true);

            document.addEventListener('mouseenter', function(ev) {
                try {
                    const el = ev.target;
                    const fp = fingerprint(el);
                    window.__hover_events.push({type:'mouseenter', time: Date.now(), target: fp});
                } catch(e){}
            }, true);

            // mutation observer for DOM additions/removes/attr changes
            const mo = new MutationObserver(function(muts){
                muts.forEach(m => {
                    if (m.addedNodes && m.addedNodes.length) {
                        m.addedNodes.forEach(n => {
                            try {
                                if (n.outerHTML) {
                                    window.__dom_mutations.push({type:'added', time:Date.now(), html: n.outerHTML.slice(0,1500)});
                                }
                            } catch(e){}
                        });
                    }
                    if (m.removedNodes && m.removedNodes.length) {
                        m.removedNodes.forEach(n => {
                            try {
                                if (n.outerHTML) {
                                    window.__dom_mutations.push({type:'removed', time:Date.now(), html: n.outerHTML.slice(0,1500)});
                                }
                            } catch(e){}
                        });
                    }
                    if (m.type === 'attributes') {
                        try {
                            window.__dom_mutations.push({type:'attr', time:Date.now(), name:m.attributeName, target: (m.target && m.target.outerHTML) ? m.target.outerHTML.slice(0,600) : ''});
                        } catch(e){}
                    }
                });
            });
            mo.observe(document.documentElement || document.body, { childList: true, subtree: true, attributes: true, attributeOldValue: true });
        })();
        """
        page.evaluate(install_script)

    # -------------------------
    # Exploration policy
    # -------------------------
    def _explore_page(self, page: Page, total_time: float = 6.0):
        """
        Moves the mouse in a grid and random walks to trigger hover effects.
        The policy intentionally avoids clicking and relies on pointer events.
        """
        vp = page.viewport_size or {"width": 1280, "height": 800}
        w, h = vp["width"], vp["height"]

        start = time.time()
        # grid parameters
        rows = max(3, min(6, int(math.sqrt(total_time) * 2)))
        cols = rows
        cell_w = w / cols
        cell_h = h / rows

        # 1) sweep grid (coarse)
        for r in range(rows):
            for c in range(cols):
                if time.time() - start > total_time:
                    return
                # center of cell with slight random offset
                cx = (c + 0.5) * cell_w + random.uniform(-cell_w*0.15, cell_w*0.15)
                cy = (r + 0.5) * cell_h + random.uniform(-cell_h*0.15, cell_h*0.15)
                try:
                    page.mouse.move(cx, cy, steps=random.randint(6,20))
                except Exception:
                    # try scroll then move
                    try:
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.2)")
                        page.mouse.move(cx, cy, steps=6)
                    except:
                        pass
                # small dwell to allow reveal
                time.sleep(0.25 + random.random()*0.25)

        # 2) random micro-walks (focus on interactive hotspots recorded so far)
        # Get current hover events to find hotspots
        try:
            events = page.evaluate("() => window.__hover_events.slice(0)")
        except Exception:
            events = []

        # compute hotspots (buckets by bounding box center)
        centers = []
        for ev in events:
            try:
                t = ev.get("target")
                if t and t.get("bbox") and t["bbox"]["w"] > 3 and t["bbox"]["h"] > 3:
                    bx = t["bbox"]["x"] + t["bbox"]["w"] / 2
                    by = t["bbox"]["y"] + t["bbox"]["h"] / 2
                    centers.append((bx, by))
            except:
                continue

        random.shuffle(centers)
        for (cx, cy) in centers[:10]:
            if time.time() - start > total_time:
                return
            # micro-jitter around center
            for _ in range(random.randint(1,3)):
                nx = cx + random.uniform(-12, 12)
                ny = cy + random.uniform(-12, 12)
                try:
                    page.mouse.move(nx, ny, steps=random.randint(4,12))
                except Exception:
                    pass
                time.sleep(0.18 + random.random()*0.12)

        # 3) exploratory spiral across page (to capture overlays appearing on edges)
        t = 0
        while time.time() - start < total_time:
            angle = random.random() * 2 * math.pi
            radius = min(w, h) * (0.1 + random.random() * 0.4)
            cx = w/2 + math.cos(angle) * radius
            cy = h/2 + math.sin(angle) * radius
            try:
                page.mouse.move(cx, cy, steps=random.randint(6,18))
            except Exception:
                pass
            time.sleep(0.2 + random.random()*0.15)

    # -------------------------
    # Aggregate events + mutations -> discoveries
    # -------------------------
    def _aggregate_events(self, page: Page, events: List[Dict], mutations: List[Dict]) -> List[Dict]:
        """
        Build clusters of hover targets and identify revealed nodes (links/buttons/text) near the time of hover events.
        Approach:
        - Count occurrences of fingerprint targets in events
        - For each top target, search the DOM for nodes whose bounding boxes overlap the target area
          and which are currently visible (computed style)
        - For each revealed node, capture short text and href if present
        """
        # count targets
        counter = Counter()
        target_samples = defaultdict(list)
        for ev in events:
            t = ev.get("target")
            if not t:
                continue
            key = f"{t.get('tag')}|{t.get('cls')}|{t.get('idx')}|{t.get('bbox')['x']}|{t.get('bbox')['y']}|{t.get('txt')[:40]}"
            counter[key] += 1
            target_samples[key].append(t)

        top = counter.most_common(12)
        discoveries = []

        for key, cnt in top:
            samples = target_samples[key]
            # use latest sample for bbox and text
            sample = samples[-1]
            bbox = sample.get("bbox", {})
            # Query visible nodes overlapping the area around bbox
            query_script = r"""
            (bbox) => {
                const out = [];
                function rectsOverlap(a,b){
                    return !(a.right < b.left || a.left > b.right || a.bottom < b.top || a.top > b.bottom);
                }
                const area = {left: bbox.x - 8, top: bbox.y - 8, right: bbox.x + bbox.w + 8, bottom: bbox.y + bbox.h + 8};
                const nodes = Array.from(document.querySelectorAll('body *'));
                for (const n of nodes){
                    try {
                        const r = n.getBoundingClientRect();
                        const rc = {left: r.x, top: r.y, right: r.x + r.width, bottom: r.y + r.height};
                        if (r.width < 6 || r.height < 6) continue;
                        if (!rectsOverlap(area, rc)) continue;
                        const cs = getComputedStyle(n);
                        if (cs && cs.display !== 'none' && cs.visibility !== 'hidden' && parseFloat(cs.opacity||1) > 0.03) {
                            out.push({
                                tag: n.tagName.toLowerCase(),
                                text: (n.innerText || n.textContent || '').trim().slice(0,300),
                                href: n.getAttribute ? n.getAttribute('href') : null,
                                outer: n.outerHTML ? n.outerHTML.slice(0,800) : null,
                                bbox: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)}
                            });
                        }
                    } catch(e){}
                }
                return out.slice(0,80);
            }
            """
            try:
                revealed = page.evaluate(query_script, {"x": bbox.get("x",0), "y": bbox.get("y",0), "w": bbox.get("w",0), "h": bbox.get("h",0), "bbox": {"x": bbox.get("x",0),"y":bbox.get("y",0),"w":bbox.get("w",0),"h":bbox.get("h",0)}})
            except Exception:
                revealed = []

            # filter revealed to keep those likely revealed by hover (exclude the trigger itself)
            filtered = []
            for r in revealed:
                # discard trivial empty text nodes unless they have href
                if (not r.get("text")) and not r.get("href"):
                    continue
                filtered.append(r)

            discoveries.append({
                "fingerprint_key": key,
                "count": cnt,
                "sample": sample,
                "revealed": filtered[:12]
            })

        # sort by count then number of revealed children
        discoveries = sorted(discoveries, key=lambda d: (d["count"], len(d["revealed"])), reverse=True)
        return discoveries

    # -------------------------
    # Popup detection & enrichment
    # -------------------------
    def _detect_popups(self, page: Page, dialogs: List[Dict], popup_pages: List[Any]) -> List[Dict]:
        pop_res = []
        # include Playwright dialog events first
        for d in dialogs:
            pop_res.append({"type": "browser_dialog", "message": d})

        # top overlays / role=dialog elements
        try:
            overlays = page.evaluate(r"""
                () => {
                    const res = [];
                    // role-based dialogs
                    document.querySelectorAll('[role="dialog"], [aria-modal="true"]').forEach(el => {
                        const title = (el.querySelector && (el.querySelector('h1,h2,h3')?.innerText || el.querySelector('.title')?.innerText)) || '';
                        const buttons = Array.from(el.querySelectorAll('a,button')).slice(0,8).map(b => ({text: (b.innerText||b.textContent||'').trim().slice(0,60), href: b.getAttribute ? b.getAttribute('href') : null}));
                        res.push({type:'role_dialog',title,buttons,outer: el.outerHTML ? el.outerHTML.slice(0,800) : null});
                    });
                    // fixed/high z-index overlays
                    const cand = Array.from(document.querySelectorAll('body *')).filter(el => {
                        try {
                            const cs = getComputedStyle(el);
                            return (cs.position==='fixed' || cs.position==='sticky' || cs.position==='absolute') && parseInt(cs.zIndex||0) > 40 && (el.offsetWidth>80 || el.offsetHeight>40);
                        } catch(e){ return false; }
                    }).slice(0,6);
                    cand.forEach(el => {
                        const title = (el.querySelector && (el.querySelector('h1,h2,h3')?.innerText || el.querySelector('.title')?.innerText)) || '';
                        const buttons = Array.from(el.querySelectorAll('a,button')).slice(0,8).map(b => ({text: (b.innerText||b.textContent||'').trim().slice(0,60), href: b.getAttribute ? b.getAttribute('href') : null}));
                        res.push({type:'overlay',title,buttons,outer: el.outerHTML ? el.outerHTML.slice(0,800) : null});
                    });
                    return res;
                }
            """)
            if overlays:
                pop_res.extend(overlays)
        except Exception:
            pass

        # include pages opened as popups (note: popup_pages are Playwright Page objects; we only record count)
        if popup_pages:
            pop_res.append({"type": "popup_window", "count": len(popup_pages)})

        return pop_res

    # -------------------------
    # Safe click verification (open hrefs in new context)
    # -------------------------
    def _safe_click_verify(self, browser, discoveries: List[Dict], result: Dict[str, Any], timeout=3.0):
        """
        For each discovered revealed link with href, open in a new context + new page (not the main context),
        wait for navigation or timeout, then close. This prevents messing with the original page state.
        """
        verified = []
        ctx = browser.new_context()
        p = ctx.new_page()
        for d in discoveries:
            for r in d.get("revealed", []):
                href = r.get("href")
                if not href:
                    continue
                try:
                    # naive normalization
                    if href.startswith("javascript:") or href.startswith("#"):
                        continue
                    # open in new page
                    pg = ctx.new_page()
                    pg.goto(href, wait_until="domcontentloaded", timeout=int(timeout*1000))
                    verified.append({"href": href, "status": "opened", "url": pg.url})
                    pg.close()
                except Exception as e:
                    verified.append({"href": href, "status": f"error: {e}"})
        p.close()
        ctx.close()
        result["click_verification"] = verified

    # -------------------------
    # Tiny Gherkin generator
    # -------------------------
    def _generate_gherkin(self, result: Dict[str, Any]) -> str:
        """
        Create two scenarios:
         - popup scenario (if popups exist)
         - hover scenario (top discovery)
        """
        url = result.get("url")
        pop = result.get("popup_discoveries", [])
        hover = result.get("hover_discoveries", [])

        lines = []
        lines.append(f'Feature: Validate hover and popup interactions for "{url}"')
        lines.append("")

        # Popup scenario
        if pop:
            # pick the first popup-ish discovery that has a title or buttons
            candidate = None
            for p in pop:
                if p.get("title") or (p.get("buttons") and len(p["buttons"])>0):
                    candidate = p
                    break
            if candidate:
                title = candidate.get("title") or "Popup/Overlay"
                buttons = candidate.get("buttons") or []
                cancel_label = buttons[0]["text"] if buttons else "Cancel"
                continue_label = buttons[1]["text"] if len(buttons) > 1 else "Continue"
                lines.append(f"Scenario: Validate popup/overlay behavior - \"{title}\"")
                lines.append(f'  Given the user is on "{url}"')
                lines.append(f'  When the user triggers the action that opens the popup') 
                lines.append(f'  Then a pop-up/overlay should appear with title \"{title}\"')
                if buttons:
                    btns = '", "'.join([b["text"] for b in buttons[:2]])
                    lines.append(f'  And the pop-up should contain buttons \"{btns}\"')
                    # cancel flow
                    lines.append(f'  When the user clicks the \"{cancel_label}\" button')
                    lines.append(f'  Then the pop-up should close and the user should remain on the same page')
                    # continue flow
                    lines.append(f'  When the user triggers the popup again and clicks the \"{continue_label}\" button')
                    lines.append(f'  Then the page should navigate to the target link (if any)')
                else:
                    lines.append('  # No actionable buttons detected in popup; manual verification required')
                lines.append("")

        # Hover scenario
        if hover:
            top = hover[0]
            trigger_txt = top["sample"].get("txt") or f"{top['sample'].get('tag')}"
            # pick first revealed link if any
            revealed_links = [r for r in top.get("revealed", []) if r.get("href")]
            lines.append(f'Scenario: Validate hover-based interaction for \"{trigger_txt[:60]}\"')
            lines.append(f'  Given the user is on "{url}"')
            lines.append(f'  When the user hovers over the UI element that appears like \"{trigger_txt[:60]}\"')
            if revealed_links:
                link = revealed_links[0]
                link_text = link.get("text") or link.get("href")
                lines.append(f'  Then a dropdown/overlay should appear containing a link \"{link_text}\"')
                lines.append(f'  When the user clicks the link \"{link_text}\"')
                lines.append(f'  Then the page URL should change to \"{link.get("href")}\"')
            else:
                # fallback: verify revealed nodes visible
                if top.get("revealed"):
                    sample_text = top["revealed"][0].get("text") or top["revealed"][0].get("tag")
                    lines.append(f'  Then a dropdown/overlay should appear containing text \"{sample_text}\"')
                else:
                    lines.append('  Then a hover-activated element should become visible (manual check)')
            lines.append("")

        if not pop and not hover:
            lines.append("  # No hover interactions or popups detected automatically. Manual checks required.")
            lines.append("")

        return "\n".join(lines)