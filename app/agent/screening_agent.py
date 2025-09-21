from langchain_core.tools import tool
from agent.lisa import Lisa
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.prompts import PromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage
import uuid

class ScreeningQuestionAgent(Lisa):
    question_prompt = ("""You are a professional Talent Scout who do Screening"""
              """Based on this job description:"""
              """{job_description}"""
              """Write a list of relevant screening question to ask for a candidate. max: 3 question"""
              """"""
              )
    
    starter_message_prompt = ("""You are a professional Talent Scout who do Screening"""
              """Based on this job opening description:"""
              """{job_description}"""
              """Write a message to reach out a talent for that job"""
              """"""
              )
    
    reach_out_prompt = ("""Your name is Lisa, a professional HR Talent Scout. You will:
                        - Ask wether user interested with the job offer
                        - if no, end the conversation by saying thank you. Not accepting any user chat
                        - if yes, Ask the screening question and update talent candidate status to "100" (call: update_candidate)
                        - After all screening question answered, update candidate status to give Assesment Link (call: get_assessment_link)
                        - when user confirmed assesment is finished, update candidate status to "101" (update_candidate) and trigger evaluate_job_opening_progress()
                        """

                        """Job Description"""
                        "{job_description}"
                        """Screening Question:"""
                        "{screening_question}"
                        """Talent Information:"""
                        "{talent_information}"

                        )

    def createQuestion(self, job_description):
        prompt = PromptTemplate.from_template(self.question_prompt)
        formatted_prompt = prompt.format(job_description=job_description)
        messages = [
            HumanMessage(formatted_prompt)
        ]
        response = ChatOpenAI().invoke(messages)

        sess = self.get_session("automated", str(uuid.uuid4()))
        sess.add_messages(messages)
        sess.add_ai_message(response)

        return response
    
    def generateMessageStarter(self, job_description):
        prompt = PromptTemplate.from_template(self.starter_message_prompt)
        formatted_prompt = prompt.format(job_description=job_description)
        messages = [
            HumanMessage(formatted_prompt)
        ]
        response = ChatOpenAI().invoke(messages)

        sess = self.get_session("automated", str(uuid.uuid4()))
        sess.add_messages(messages)
        sess.add_ai_message(response)

        return response

    
    def reachOutTalent(self, chat_user_id, job_description, screening_question, talent_information):
        prompt = PromptTemplate.from_template(self.reach_out_prompt)
        formatted_prompt = prompt.format(
            job_description=job_description,
            screening_question=screening_question,
            talent_information=talent_information
        )
        messages = [
            SystemMessage(formatted_prompt)
        ]
        response = ChatOpenAI().invoke(messages)

        sess = self.get_session(chat_user_id, str(uuid.uuid4()))
        sess.add_messages(messages)
        sess.add_ai_message(response)

        return response



@tool
def generate_screening_question(job_description):
    """Generate Screening Question for Candidate

    Required for crafting context prompt for TALENT_REACH_OUT
    Args:
        job_description: str - job description detail
    """
    from agent.lisa import Lisa
    from langchain_core.messages import HumanMessage

    response = Lisa().invoke([
        HumanMessage(content=("""> Given a job description:"""
          f"{job_description}"
          """> Based on above job description, craft 4 question for screening candidate.
            """))
    ])
    return response