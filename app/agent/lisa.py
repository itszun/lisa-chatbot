from agent.base_agent import BaseLisa

class Lisa(BaseLisa):
    agent = {}
    is_new = False

    def __init__(self, is_new=False):
        print("LISA INITIATE")
        self.is_new = is_new
