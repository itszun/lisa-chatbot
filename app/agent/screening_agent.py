from langchain_core.tools import tool
from agent.base_agent import BaseLisa
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.prompts import PromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage
import uuid
from prompt import TemplatePrompt as TP

class ScreeningQuestionAgent(BaseLisa):
    question_prompt = ("""You are a professional Talent Scout who do Screening"""
              """Based on this job description:"""
              """{job_opening_detail}"""
              """Write a list of relevant screening question to ask for a candidate. max: 3 question"""
              """"""
              )
    
    starter_message_prompt = ("""You are a professional Talent Scout who do Screening"""
              """Based on this job opening description:"""
              """{job_opening_detail}"""
              """Write a message to reach out a talent for that job"""
              """"""
              )
    
    reach_out_prompt = ("""Your name is Lisa, a professional HR Talent Scout currently reach out to ask Talent for their interest and do screening for a job opening. You will:
                        - Ask wether user interested with the job offer
                        - if no, end the conversation by saying thank you. Not accepting any user chat
                        - if yes, Ask the screening question and update talent candidate status to "100" (call: update_candidate)
                        - After all screening question answered, update candidate status to give Assesment Link (call: get_assessment_link)
                        - when user confirmed assesment is finished, update candidate status to "101" (update_candidate) and trigger evaluate_job_opening_progress()
                        - after assesment finished, give option to schedule interview and let user choose
                        - if confirmed interview schedule, update candidate to "102" (Interview)
                        """
                        f"{TP.USE_MARKDOWN}"

                        """\nJob Opening Details:\n"""
                        "{job_opening_detail}"
                        """\n\nTalent Information:\n"""
                        "{talent_information}"
                        """\n\nCandidate Status:\n"""
                        "{candidate_information}"
                        )

    def createQuestion(self, job_opening_detail):
        prompt = PromptTemplate.from_template(self.question_prompt)
        formatted_prompt = prompt.format(job_opening_detail=job_opening_detail)
        messages = [
            HumanMessage(formatted_prompt)
        ]
        response = self.invoke(messages)

        sess = self.get_session("automated", str(uuid.uuid4()))
        sess.add_messages(messages)
        sess.add_ai_message(response)

        return response
    
    def generateMessageStarter(self, job_opening_detail):
        prompt = PromptTemplate.from_template(self.starter_message_prompt)
        formatted_prompt = prompt.format(job_opening_detail=job_opening_detail)
        messages = [
            HumanMessage(formatted_prompt)
        ]
        response = ChatOpenAI().invoke(messages)
        messages = [*messages, response]

        session_id = str(uuid.uuid4())
        sess = self.get_session("automated", session_id)
        sess.add_messages(messages)

        self.session_titles("automated", session_id, messages)

        return response

    
    def reachOutTalent(self, chat_user_id, job_opening_detail, talent_information, candidate_information, chat_starter):
        prompt = PromptTemplate.from_template(self.reach_out_prompt)
        formatted_prompt = prompt.format(
            job_opening_detail=job_opening_detail,
            talent_information=talent_information,
            candidate_information=candidate_information
        )
        messages = [
            SystemMessage(formatted_prompt)
        ]
        messages = [*messages, chat_starter]

        session_id = str(uuid.uuid4())
        sess = self.get_session(chat_user_id, session_id)
        sess.add_messages(messages)

        self.session_titles(chat_user_id, session_id, messages)

        return chat_starter

