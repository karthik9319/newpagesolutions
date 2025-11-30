from crew import TestGeneration

def run():
    inputs = {"url": "https://www.nike.com/in/"}
    result = TestGeneration().crew().kickoff(inputs=inputs)
    print(result)

run()