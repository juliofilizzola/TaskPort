"""Representações mínimas dos recursos do Trello utilizados pela aplicação."""

from pydantic import BaseModel, ConfigDict, Field


class _TrelloModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class TrelloBoard(_TrelloModel):
    id: str
    name: str
    url: str | None = None
    closed: bool = False


class TrelloList(_TrelloModel):
    id: str
    name: str
    closed: bool = False


class TrelloLabel(_TrelloModel):
    id: str
    name: str = ""
    color: str | None = None


class TrelloCard(_TrelloModel):
    id: str
    name: str
    desc: str = ""
    closed: bool = False
    id_list: str | None = Field(default=None, alias="idList")
    id_labels: list[str] = Field(default_factory=list, alias="idLabels")
    url: str | None = None


class TrelloCheckItem(_TrelloModel):
    id: str
    name: str
    state: str = "incomplete"

    @property
    def complete(self) -> bool:
        return self.state == "complete"


class TrelloChecklist(_TrelloModel):
    id: str
    name: str
    check_items: list[TrelloCheckItem] = Field(default_factory=list, alias="checkItems")


class BoardOut(BaseModel):
    id: str
    name: str
    url: str | None = None
