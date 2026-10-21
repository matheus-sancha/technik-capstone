"""A scripted stand-in for the Foundry model, run through Agent Framework's real function-calling loop."""
from agent_framework import BaseChatClient, ChatResponse, Content, FunctionInvocationLayer, Message


class FakeChatClient(FunctionInvocationLayer, BaseChatClient):
    """First turn: request the scripted tool calls, if any. Next turn: answer with the scripted text.

    It records what the agent sent, so a test can see the instructions and the tools the model was offered.
    """

    def __init__(self, calls=(), answer="", **kwargs):
        super().__init__(**kwargs)
        self.calls, self.answer, self.seen = list(calls), answer, []

    async def _inner_get_response(self, *, messages, stream, options, **kwargs):
        self.seen.append(options)
        answered = any(c.type == "function_result" for m in messages for c in m.contents)
        if self.calls and not answered:
            contents = [Content.from_function_call(f"call_{i}", name, arguments=args)
                        for i, (name, args) in enumerate(self.calls)]
        else:
            contents = [Content.from_text(self.answer)]
        return ChatResponse(messages=[Message(role="assistant", contents=contents)])
