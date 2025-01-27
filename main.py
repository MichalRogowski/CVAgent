import asyncio

from dotenv import load_dotenv
import os
import subprocess
import logging

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import TextMentionTermination
from autogen_agentchat.teams import Swarm
from autogen_agentchat.ui import Console
from autogen_ext.models.openai import OpenAIChatCompletionClient
from typing import Any, Mapping

load_dotenv()
openai_model_4o_client = OpenAIChatCompletionClient(
    model="gpt-4o",
    api_key=os.getenv("OPENAI_API_KEY"),
)

openai_model_mini_client = OpenAIChatCompletionClient(
    model="gpt-4o-mini",
    api_key=os.getenv("OPENAI_API_KEY"),
)

ollama_33 = OpenAIChatCompletionClient(
    model="llama3.3:latest",
    base_url="http://localhost:11434/v1",
    api_key="placeholder",
    model_info={
        "vision": False,
        "function_calling": True,
        "json_output": False,
        "family": "unknown",
    },
)


def get_file_content(filename: str) -> str:
    with open(f"{filename}", "r", encoding="utf-8") as file:
        content = file.read()
        return content


async def store_yaml(yaml: str):
    with open("CV.yaml", "w") as text_file:
        text_file.write(yaml)
        return "SUCCESS"


def _run_command(command: str):
    logging.debug(f"Command: {command}")
    result = subprocess.run(command, shell=True, capture_output=True)
    if result.stderr:
        raise subprocess.CalledProcessError(
            returncode=result.returncode,
            cmd=result.args,
            stderr=result.stderr
        )
    if result.stdout:
        logging.debug(f"Command Result: {result.stdout.decode('utf-8')}")

    lines = result.stdout.decode('utf-8').split('\n')
    return '\n'.join(lines)


async def generate_cv():
    return _run_command("rendercv render CV.yaml")


def generate_cv_taking_swarm() -> Swarm:
    # Create the planner.
    planning_agent = AssistantAgent(
        "planning_agent",
        description="An agent for planning tasks, this agent should be the first to engage when given a new task.",
        model_client=openai_model_mini_client,
        handoffs=["cv_writer", "yaml_writer"],
        system_message="""
           You are a **planning agent**. Your role is to:

            1. **Break down** complex tasks into smaller, manageable subtasks.  
            2. **Delegate** these subtasks to the appropriate agents:  
                - **writer_agent**: A helpful AI assistant specialized in writing ATS-optimized CVs.  
                - **critic_agent**: Provides constructive feedback on the CV to ensure it is ATS optimized.  
                - **yaml_writer**: Converts the final **approved** CV into YAML format only after all feedback has been 
                addressed.

            You **do not execute** tasks yourself; you **only plan and delegate** tasks.

            ---

            ### **Task Delegation Format**
            1. <agent> : <task>

            ---

            ### **Completion**

            When the `yaml_writer` confirms a **successful render** of the CV, **summarize** the entire interaction 
            between agents, then use: 
            **TERMINATE**
            to conclude the process.
           """,
    )

    advert = get_file_content("advert.txt")
    # Create the CV Writing agent.
    writing_agent = AssistantAgent(
        "cv_writer",
        model_client=openai_model_mini_client,
        description="An agent for Writing ATS optimised CV, and incorporating feedback",
        handoffs=["planning_agent", "cv_critic"],
        system_message=f"""
        You are an experienced writer specialized in creating ATS-optimized CVs. Your task is to produce a CV that:
        1. Analyse the **advert** {advert}
        2. Incorporates all **commercial experiences**.
        3. Optimise for **Applicant Tracking Systems (ATS)**.

        In the final CV Edit or modify my skills as needed, based on other experience with personal highlights.

        Here are guidelines how to write a proper CV:
        1. **Keep it Clear and Easy to Read** 
         - Your resume should immediately highlight key info: years of experience, technical skills, 
         and leadership/significant roles (if any). 
         - Avoid clutter. Use clean formatting with clear sections so I don’t have to search for the basics. 

        2. **Be Selective with  Skills** 
         - Listing every tech skill you’ve ever touched does not help. Instead, focus on those that directly align with 
         the job description. Edit or modify my skills as needed, based on other experiences with personal highlights. 
         - Highlight your proficiency in key languages and tools rather than overwhelming the reader with a long list.
         - When possible make sure to use Keywords from the **advert**, if the skills from experience or 
         skills are similar

        3. **Describe, Don’t Overwhelm** 
         - Each project should tell a story in **3-6** concise bullet points. Stick to the most impactful details: 
         **what you built, the outcome, and the tools used, for more senior positions add more bullet points. **

        4. **Use Simple Language** 
         - Don’t write your resume like a research paper. 
         - Show you can explain complex ideas clearly. 
         - If I need to reread a sentence to understand it, you’ve lost me. 

        5. **Tailor Your Resume to the Job the job advert**
        - Don’t make recruiters sift through irrelevant details. 
        - Customize your resume to emphasize skills and experience that match the role. 

        A simple, well-written resume tells me: 
        - You know how to communicate effectively. 
        - You understand the job requirements and have the experience for it. 

        The most important requirements are:
        1. You include all positions from my experience
        2. You make sure that CV sounds like written by a human
        3. You make it optimised for ATS and Hiring Manager

        After drafting the CV, you will **hand off** it to the cv_critic **for feedback**.
        • Whenever you receive feedback, you must document and apply it using the following format:
            1. <feedback> : <changes>

        Continue revising the CV and resubmitting it to the cv_critic until the CV has been **approved twice** by 
        the cv_critic. Only when you have received **two separate approvals** from the cv_critic should you 
        **hand off** the final CV to the planning_agent.

        **Important Guidelines**
        •	Do not submit the final CV to the planning_agent until you have **two approvals** from the cv_critic.
        •	Every time you receive feedback, **apply** it and **show your changes** in the specified format.
        •	Ensure **all commercial experiences** are clearly listed.

        Stop and **handoff back to planning_agent** once the CV receives its **second approval** from the cv_critic.           
           """,
    )

    # Create the critic agent.
    critiquing_agent = AssistantAgent(
        "cv_critic",
        handoffs=["cv_writer"],
        description="An agent for Critiquing provided CV, to make it more aligned with advert and ATS",
        system_message=""""
        You are an ATS expert who understands what hiring managers look for in a CV based on the provided job 
        advertisement. Your role is to:
        1. Review the CV presented by the cv_writer.
        2. Provide constructive feedback that will help the cv_writer improve the CV.
        3. Require two approvals before finalizing:
            • After each CV revision, you must assess whether it meets the required standards.
            • If it does not, provide further feedback for improvement.
            • If it does, you approve the CV.
        4. Upon your second approval, write: **'Feedback Addressed APPROVED TWICE'** and instruct to 
        HANDOFF TO cv_writer.

        Stop and finalize your role once you have given your **second approval** and posted the message above.
           """,
        model_client=openai_model_mini_client,
    )

    structure_of_the_yaml = get_file_content("structure_of_the_yaml_input_file.md")
    example_yaml = get_file_content("example.yaml")

    yaml_writer_agent = AssistantAgent(
        "yaml_writer",
        handoffs=["planning_agent"],
        tools=[store_yaml, generate_cv],
        description="An agent for generating YAML based on the CV provided by cv_writer and approved by critic, "
                    "storing and rendering it",
        system_message=f"""
           You are the "cv_renderer" agent. Your role is to follow a multi-step process, using specific tools, 
           to generate a PDF version of a CV. Below are your instructions:
---

### Step 1: Create the YAML
- When a CV is provided, produce a YAML file that adheres to the **rendercv** library’s documented structure.
    • Parse the Documentation here: {structure_of_the_yaml}.
    • Analyse the correct example YAML here: {example_yaml}.
    • Generate or fix the YAML file so it strictly conforms to the documentation’s requirements or **structure
     is consistent** with the example.
    • Check nested structures to ensure they also follow the documentation and example.
    • Output files should use the default.

- **Important**: Apply:
  - `theme: engineeringclassic`
  - `locale.phone_number_format: international`

---

### Step 2: Store & Generate
1. After creating the YAML, **store** it using the `store_yaml` tool.
2. Then **generate the CV PDF** by invoking the `generate_cv` tool.

---

### Step 3: Handle Failures
If the `generate_cv` tool fails:

<failed_generating_instructions>
3.1. Task:
• Summarize all error messages returned by the generate_cv tool.
• Analyse the **working** example YAML here: {example_yaml}.
• For each problem find section from the **example** which would solve this problem
• Regenerate the problematic section in YAML so it strictly conforms to the **structure** found above.
• Never delete an experience from experience section. All positions have to be present.
• Check nested structures to ensure they also follow the documentation and example.  
• Return to Step 2 to store the fixed YAML and THEN generate the PDF again.
####Handoff Conditions
**IF** you have attempted to refactor the YAML **four times** and still cannot generate the PDF.
</failed_generating_instructions>

### Step 3: Handle Success - Handoff Conditions
- The CV is successfully generated by the `cv_renderer` agent **and** the PDF has been confirmed.
HANDOFF TO PLANNER AGENT and confirm **'SUCCESSFUL CV RENDER'** 
""",
        model_client=openai_model_mini_client,
        reflect_on_tool_use=True
    )

    text_termination = TextMentionTermination("TERMINATE")

    cv_making_team = Swarm(
        participants=[planning_agent, writing_agent, critiquing_agent, yaml_writer_agent],
        termination_condition=text_termination
    )
    return cv_making_team


def generate_task_for_cv_making_team() -> str:
    experience = get_file_content("CV-experience.txt")
    personal = get_file_content("CV-personal.txt")
    skills = get_file_content("CV-skills.txt")
    advert = get_file_content("advert.txt")

    task = f"""
    Write a beautiful **CV** that is **ATS optimised**.        
    The commercial experience is here {experience}.
    The skills I listed here {skills}
    Other information required in the CVs are here {personal}
    The advert of the job I apply for is here {advert}"""

    return task


async def run_cv_maker_agent(state: Mapping[str, Any]):
    cv_making_team = generate_cv_taking_swarm()
    task = generate_task_for_cv_making_team()

    try:
        if state is not {}:
            print(f"state is {state}")
            await cv_making_team.load_state(state)

        stream = cv_making_team.run_stream(task=task)
        try:
            await Console(stream)
        except Exception as e:
            print(f"Handled exception2: {e}")
            # state = await cv_making_team.save_state()
            # await cv_making_team.reset()
            # await run_cv_maker_agent(state)
            pass
    except Exception as e:
        print(f"Handled exception: {e}")
        pass


initial_state = {}
asyncio.run(run_cv_maker_agent(initial_state))
