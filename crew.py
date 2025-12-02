# crew.py
from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import CrewBase, agent, crew, task
import os
import yaml

# ---------------- LLM Configuration ----------------
llm = LLM(
    model="ollama/llama3.1",        
    base_url="http://localhost:11434"
)

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config")

def load_yaml(file_name: str):
    path = os.path.join(CONFIG_PATH, file_name)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

agents_config = load_yaml("agents.yaml")
tasks_config = load_yaml("tasks.yaml")


@CrewBase
class TestGeneration:

    # ---------- Agents ----------

    @agent
    def page_scanner(self) -> Agent:
        return Agent(
            config=agents_config["page_scanner"],
            llm=llm,
            verbose=True
        )

    @agent
    def interaction_analyzer(self) -> Agent:
        return Agent(
            config=agents_config["interaction_analyzer"],
            llm=llm,
            verbose=True
        )

    @agent
    def popup_detector(self) -> Agent:
        return Agent(
            config=agents_config["popup_detector"],
            llm=llm,
            verbose=True
        )

    @agent
    def scenario_reasoner(self) -> Agent:
        return Agent(
            config=agents_config["scenario_reasoner"],
            llm=llm,
            verbose=True
        )

    @agent
    def gherkin_writer(self) -> Agent:
        return Agent(
            config=agents_config["gherkin_writer"],
            llm=llm,
            verbose=True
        )

    # ---------- Tasks ----------

    @task
    def page_scanner_task(self) -> Task:
        return Task(
            agent=self.page_scanner(),
            config=tasks_config["page_scanner_task"]
        )

    @task
    def interaction_analyzer_task(self) -> Task:
        return Task(
            agent=self.interaction_analyzer(),
            config=tasks_config["interaction_analyzer_task"],
            context=[self.page_scanner_task()]
        )

    @task
    def popup_detector_task(self) -> Task:
        return Task(
            agent=self.popup_detector(),
            config=tasks_config["popup_detector_task"],
            context=[self.interaction_analyzer_task()]
        )

    @task
    def scenario_reasoner_task(self) -> Task:
        return Task(
            agent=self.scenario_reasoner(),
            config=tasks_config["scenario_reasoner_task"],
            context=[self.popup_detector_task()]
        )

    @task
    def gherkin_generation_task(self) -> Task:
        return Task(
            agent=self.gherkin_writer(),
            config=tasks_config["gherkin_generation_task"],
            context=[self.scenario_reasoner_task()]
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=[
                self.page_scanner(),
                self.interaction_analyzer(),
                self.popup_detector(),
                self.scenario_reasoner(),
                self.gherkin_writer()
            ],
            tasks=[
                self.page_scanner_task(),
                self.interaction_analyzer_task(),
                self.popup_detector_task(),
                self.scenario_reasoner_task(),
                self.gherkin_generation_task()
            ],
            process=Process.sequential,
            verbose=True
        )