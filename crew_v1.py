from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import CrewBase, agent, task, crew
from langchain_ollama import OllamaLLM

llm = LLM(
    api_key = "ollama",
    base_url="http://localhost:11434/v1",
    model="devstral")
# from tools.playwright_tool import PlaywrightExplorerTool

import os
import yaml

# llm = LLM(
#     api_key="ollama",
#     base_url="http://localhost:11434/v1",
#     model="gpt-oss:20b",
# )

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config")

def load_yaml(name):
    with open(os.path.join(CONFIG_PATH, name), "r") as f:
        return yaml.safe_load(f)

agents_config = load_yaml("agents.yaml")
tasks_config = load_yaml("tasks.yaml")

@CrewBase
class TestGeneration:
    
    def __init__(self):
        """Ensure configurations are loaded correctly."""
        required_agents = ["page_scanner"]
        required_tasks = ["page_scanner_task"]

        for agent in required_agents:
            if agent not in agents_config:
                raise ValueError(f"Error: Missing '{agent}' in agents.yaml")

        for task in required_tasks:
            if task not in tasks_config:
                raise ValueError(f"Error: Missing '{task}' in tasks.yaml")
    
    @agent
    def page_scanner(self):
        return Agent(
            config=agents_config["page_scanner"],
            llm=llm
        )
        
    @task
    def page_scanner_task(self):
        return Task(
            config=tasks_config["page_scanner_task"],
            agent=self.page_scanner()
        )

    
    @crew
    def crew(self) -> Crew:
        """Creates the LatestAiDevelopment crew"""
        return Crew(
        agents=self.agents, # Automatically created by the @agent decorator
        tasks=self.tasks, # Automatically created by the @task decorator
        process=Process.sequential,
        verbose=True,
        )