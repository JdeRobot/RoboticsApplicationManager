class Completion:

    def __init__(self,completion):
        self.label = completion.name
        self.name_with_symbols = completion.name_with_symbols
        self.docstring = completion.docstring()
        self.type = completion.type

def serialize_completions(completions):
    serialized = []

    for completion in completions:
        serialized.append(CompletionSerializer(Completion(completion)).data)

    return serialized


from rest_framework import serializers

class CompletionSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=200)
    name_with_symbols = serializers.CharField(max_length=200)
    type = serializers.CharField(max_length=64)
    docstring = serializers.CharField(max_length=1000)
