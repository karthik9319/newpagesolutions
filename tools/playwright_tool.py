from crewai.tools import BaseTool
from playwright.sync_api import sync_playwright

class PlaywrightExplorerTool(BaseTool):
    name: str = "playwright_explorer"
    description: str = (
        "Dynamically explores a webpage. Detects hover behavior, DOM mutations, "
        "revealed elements, and optionally verifies click interactions."
    )

    def _run(self, url: str, click_verify: bool = False):
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page()

                page.goto(url, wait_until="networkidle")

                # Inject hover listener
                page.evaluate("""
                    window._hoverEvents = [];
                    document.addEventListener('mouseover', (e) => {
                        window._hoverEvents.push({
                            tag: e.target.tagName,
                            text: e.target.innerText || '',
                            classes: e.target.className || '',
                            timestamp: Date.now()
                        });
                    });
                """)

                # Move mouse across the page to trigger hover events
                for y in range(0, page.viewport_size["height"], 80):
                    for x in range(0, page.viewport_size["width"], 120):
                        page.mouse.move(x, y)

                hover_events = page.evaluate("window._hoverEvents")

                # Optionally verify clicks
                click_results = []
                if click_verify:
                    for he in hover_events[:10]:  # prevent runaway clicks
                        try:
                            element = page.locator(f"text={he['text']}")
                            if element.count() > 0:
                                with page.expect_navigation(timeout=3000):
                                    element.first.click()
                                click_results.append({
                                    "text": he["text"],
                                    "navigation_url": page.url
                                })
                        except:
                            continue

                browser.close()

                return {
                    "hover_discoveries": hover_events,
                    "popup_discoveries": [],
                    "click_verification": click_results
                }

        except Exception as e:
            return {"error": str(e)}