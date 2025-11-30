from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import CrewBase, agent, crew, task
from tools.playwright_tool import PlaywrightExplorerTool
import os
import yaml


# llm = LLM(
#     provider="litellm",
#     api_key= "ollama",
#     model="devstral",
#     base_url="http://localhost:11434/v1"
# )

llm = LLM(
    # provider ="ollama",
    model="ollama/debstral",             # use the correct model identifier from your local ollama
    base_url="http://0.0.0.0:8000"  # no /v1 suffix
)


playwright_tool = PlaywrightExplorerTool() 

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config")

def load_yaml(name):
    with open(os.path.join(CONFIG_PATH, name), "r") as f:
        return yaml.safe_load(f)

agents_config = load_yaml("agents.yaml")
tasks_config = load_yaml("tasks.yaml")


# ---------------- Crew --------------------
@CrewBase
class TestGeneration:

    # ---------- Agents ----------
    @agent
    def page_scanner(self):
        return Agent(
            config=agents_config["page_scanner"],
            tools=[playwright_tool],
            llm=None,
            allow_delegation=False
        )

    @agent
    def interaction_probe(self):
        return Agent(
            config=agents_config["interaction_probe"],
            tools=[playwright_tool],
            llm=None,
            allow_delegation=False
        )

    @agent
    def popup_detector(self):
        return Agent(
            config=agents_config["popup_detector"],
            llm=llm
        )

    @agent
    def scenario_reasoner(self):
        return Agent(
            config=agents_config["scenario_reasoner"],
            llm=llm
        )

    @agent
    def gherkin_writer(self):
        return Agent(
            config=agents_config["gherkin_writer"],
            llm=llm
        )


    # ---------- Tasks ----------
    @task
    def page_scanner_task(self):
        return Task(
            agent=self.page_scanner(),
            config=tasks_config["page_scanner_task"],
        )
        

    @task
    def interaction_probe_task(self):
        return Task(
            agent=self.interaction_probe(),
            config=tasks_config["interaction_probe_task"],
            context=[self.page_scanner_task()],
        )

    @task
    def popup_detection_task(self):
        return Task(
            agent=self.popup_detector(),
            config=tasks_config["popup_detection_task"],
            context=[self.interaction_probe_task()],
        )

    @task
    def scenario_reasoning_task(self):
        return Task(
            agent=self.scenario_reasoner(),
            config=tasks_config["scenario_reasoning_task"],
            context=[self.popup_detection_task()],
        )

    @task
    def gherkin_generation_task(self):
        return Task(
            agent=self.gherkin_writer(),
            config=tasks_config["gherkin_generation_task"],
            context=[self.scenario_reasoning_task()],
        )


    # ---------- Crew ----------
    @crew
    def crew(self):
        return Crew(
            # llm = llm,
            agents=[
                self.page_scanner(),
                self.interaction_probe(),
                self.popup_detector(),
                self.scenario_reasoner(),
                self.gherkin_writer()
            ],
            tasks=[
                self.page_scanner_task(),
                self.interaction_probe_task(),
                self.popup_detection_task(),
                self.scenario_reasoning_task(),
                self.gherkin_generation_task()
            ],
            process=Process.sequential,
            verbose=True
        )