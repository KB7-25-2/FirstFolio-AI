from kiwipiepy import Kiwi


class KiwiTokenizer:
    searchable_tag_prefixes = (
        "N",
        "VV",
        "VA",
        "VX",
        "M",
        "XR",
        "SL",
        "SH",
        "SN",
    )

    def __init__(self) -> None:
        self._kiwi = Kiwi()

    def tokenize(self, text: str) -> list[str]:
        return [
            token.form.lower()
            for token in self._kiwi.tokenize(text)
            if token.tag.startswith(self.searchable_tag_prefixes)
        ]
