# from langchain_ollama import OllamaLLM

# llm = OllamaLLM(model="gpt-oss:20b")

# print(llm.invoke("Hello"))

# test_ollama_crewai.py
from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import CrewBase, agent, crew, task

# Setup LLM (adjust if needed)
llm = LLM(
    model="ollama/llama3",
    base_url="http://localhost:11434"
)

@CrewBase
class TestCrew:
    @agent
    def test_agent(self) -> Agent:
        return Agent(
            role="Tester",
            goal="Return a greeting",
            backstory="Simple test",
            llm=llm,
            verbose=True
        )

    @task
    def test_task(self) -> Task:
        return Task(
            description="Say hello task",
            expected_output="Hello from LLM",
            agent=self.test_agent()
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=[self.test_agent()],
            tasks=[self.test_task()],
            process=Process.sequential,
            verbose=True
        )

if __name__ == "__main__":
    result = TestCrew().crew().kickoff(inputs={})
    print("Result:", result)