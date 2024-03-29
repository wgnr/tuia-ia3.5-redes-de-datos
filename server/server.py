from datetime import datetime
from enum import Enum
from fastapi import FastAPI, Body, FastAPI, HTTPException, status, Path
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from typing import Annotated, Literal
import sys
import numpy as np
import pandas as pd
import uvicorn

app = FastAPI()

df = pd.read_parquet("events_2023.parquet")


class EventType(str, Enum):
    gratis = "gratis"
    paga = "paga"
    gorra = "gorra"


class TicketType(str, Enum):
    fijo = "FIJO"
    desde = "DESDE"
    por_mes = "POR_MES"
    agotadas = "AGOTADAS"
    total = "TOTAL"
    por_vez = "POR_VEZ"
    gratis = "GRATIS"


field_id = dict(title="Event's id", description="Event's id")
field_name = dict(title="Event's name")
field_date_start = dict(title="Event's start date",
                        description="It has to be a date in the format YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS")
field_date_end = dict(title="Event's end date",
                      description="It has to be a date in the format YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS")
field_ticket = dict(title="Event type",
                    description="An event can be free, paid or by charity donation")
field_text = dict(title="Event description",
                  description="A description of the event")


class EventNew(BaseModel):
    name: Annotated[str, Field(**field_name)]  # type: ignore
    date_start: Annotated[datetime, Field(**field_date_start)]  # type: ignore
    date_end: Annotated[datetime, Field(**field_date_end)]  # type: ignore
    ticket: Annotated[EventType | None, Field(
        **field_ticket)] = None  # type: ignore
    text: Annotated[str | None, Field(**field_text)] = None  # type: ignore
    ticket_value: Annotated[str | None,
                            Field(title="Ticket cost", description="Ticket cost. It can be 0.")] = None
    eventual_name: Annotated[str | None, Field()] = None
    eventual_direccion: Annotated[str | None, Field()] = None
    eventual_coords: Annotated[str | None, Field()] = None
    eventual_distrito: Annotated[Literal['437'] | Literal['438'] | Literal['441']
                                 | Literal['442'] | Literal['440'] | Literal['439'] | None, Field()] = None
    suspendida: Annotated[bool,
                          Field(title='is_suspended', description="Describe wether the current event is suspended")] = False
    actividad: Annotated[int | None,
                         Field(description="Groups related events")] = None
    regla: Annotated[int, Field()] = 0
    regla_er: Annotated[str | None, Field()] = None
    ticket_tipo: Annotated[TicketType | None,
                           Field(title="Ticket type")] = None
    ticket_valor: Annotated[float | None, Field(title="Ticket cost")] = None
    ticket_paga_menor_4: Annotated[bool,
                                   Field(description="Event free for children under 4 years-old")] = True


class EventEdit(EventNew):
    name: Annotated[str | None, Field(**field_name)]  # type: ignore
    date_start: Annotated[datetime | None, Field(
        **field_date_start)]  # type: ignore
    date_end: Annotated[datetime | None, Field(
        **field_date_end)]  # type: ignore
    ticket: Annotated[EventType | None, Field(**field_ticket)]  # type: ignore


class Event(EventNew):
    id: Annotated[int, Field(**field_id)]  # type: ignore


class EventSearch(BaseModel):
    name: Annotated[str | None, Field(
        title="Event name", description="Enter any key word contained in the event name")] = None
    ticket: Annotated[set[EventType] | None, Field(
        title="Event type", description="An event can be free, paid or by charity donation")] = None
    ticket_tipo: Annotated[set[TicketType] | None, Field(
        title="Ticket type", description="For those events that are paid, you can choose the type of ticket")] = None
    ticket_valor_min: Annotated[float | None, Field(
        title="Ticket min value", description="It has to be a number greater or equal than 0", ge=0)] = None
    ticket_valor_max: Annotated[float | None, Field(
        title="Ticket max value", description="It has to be a number greater than 0", gt=0)] = None
    ticket_paga_menor_4: Annotated[bool | None, Field(
        title="Children under 4 pays?", description="Free or charge for children under 4 years old")] = None
    date_start: Annotated[datetime | None, Field(
        title="Filter by start date", description="It has to be a date in the format YYYY-MM-DD or in the format YYYY-MM-DDTHH:MM:SS")] = datetime(2023, 1, 1)
    date_end: Annotated[datetime | None, Field(
        title="Filter by end date", description="It has to be a date in the format YYYY-MM-DD or in the format YYYY-MM-DDTHH:MM:SS")] = datetime(2024, 1, 1)
    eventual_direccion: Annotated[str | None, Field(
        title="Filter by address", description="Enter any key word contained in the event address")] = None
    actividad: Annotated[int | None, Field(
        title="Activity Number", description="Find all events related to a certain activity number")] = None


def parse_params(df: pd.DataFrame, params: dict[str, str | set | float | bool | datetime]):
    mask = pd.Series([True]*len(df), index=df.index)
    for k, v in params.items():
        if type(v) is set:
            mask = (mask) & (df[k].isin(v))
        elif type(v) is str:
            mask = (mask) & (df[k].str.contains(v, case=False))
        elif k == "date_start":
            mask = (mask) & (df[k] >= pd.to_datetime(v))  # type: ignore
        elif k == "date_end":
            mask = (mask) & (df[k] <= pd.to_datetime(v))  # type: ignore
        elif k == "ticket_valor_min":
            mask = (mask) & (df["ticket_valor"] >= v)
        elif k == "ticket_valor_max":
            mask = (mask) & (df["ticket_valor"] <= v)
        else:
            mask = (mask) & (df[k] == v)

    return mask


@app.post("/event",
          response_model=Event,
          status_code=status.HTTP_201_CREATED,
          tags=["events"],
          summary="Create a new event",
          description="Include the minimal fields to create a new event. Check schema for more informacion. Event's id is assigned automatically."
          )
def create_event(new_event: Annotated[EventNew,
                                      Body(title="Event's data",
                                           description="Include only the fields that you would like to update.")]):
    global df
    event_dict = new_event.dict()
    if not event_dict.get("actividad"):
        event_dict["actividad"] = int(df.actividad.max()+1)
    if not event_dict.get("id"):
        event_dict["id"] = int(df.id.max()+1)

    new_row = pd.DataFrame.from_dict(
        [jsonable_encoder(event_dict)])  # type: ignore
    df = pd.concat([df, new_row])
    return df.iloc[-1].replace([np.nan], None).to_dict()

@app.get("/events",
         response_model=list[Event],
         tags=["events"],
         summary="Get first 1000 events",
         description="Get first 1000 events")
def get_events():
    selection = df.head(1000)
    return selection.replace([np.nan], None).to_dict("records")


@app.get("/events/free",
         response_model=list[Event],
         tags=["events"],
         summary="Get top 100 free events",
         description="Get the first 100 events where the ticket is 'gratis'")
def get_free_events():
    selection = df[df.ticket == 'gratis'].head(100)
    return selection.replace([np.nan], None).to_dict("records")


@app.get("/event/{event_id}",
         response_model=list[Event],
         tags=["events"],
         summary="Get event by id",
         description="Get one event by its id")
def get_event(event_id: Annotated[int,
                                  Path(title="Event's id", description="Event's id")]):
    selection = df[df.id == event_id]
    if not len(selection):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")

    return selection.replace([np.nan], None).to_dict("records")


@app.put("/event/{event_id}",
         response_model=list[Event],
         tags=["events"],
         summary="Update event by id",
         description="Update one or more fields of an event by its id"
         )
def put_event(event_id: Annotated[int,
                                  Path(title="Event's id", description="Event's id")],
              body: Annotated[EventEdit,
                              Body(
                                  title="Event's data",
                                  description="Include only the fields that you would like to update."
                              )]):
    if not len(df[df.id == event_id]):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")

    event_dict = body.dict(exclude_unset=True)
    df.loc[df.id == event_id, event_dict.keys()] = list(  # type: ignore
        map(jsonable_encoder, event_dict.values()))
    return df.loc[df.id == event_id].replace([np.nan], None).to_dict("records")


@app.delete("/event/{event_id}",
            response_model=list[Event],
            tags=["events"],
            summary="Suspend an event by id")
def delete_event(event_id: Annotated[int,
                                     Path(title="Event's id", description="Event's id")]):
    if not len(df[df.id == event_id]):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")

    df.loc[df.id == event_id, "suspendida"] = True
    return df.loc[df.id == event_id].replace([np.nan], None).to_dict("records")


@app.get("/activity/{activity_id}",
         response_model=list[Event],
         tags=["activities"],
         summary="Get events by activity number",
         description="Get a list of related events by the same activity number",
         )
def get_activity(activity_id: Annotated[int,
                                        Path(title="Activity Number",
                                             description="Find all events related to a certain activity number")]):
    selection = df[df.actividad == activity_id]
    if not len(selection):
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "Activity has no events")
    return selection.replace([np.nan], None).to_dict("records")


@app.post("/search",
          response_model=list[Event],
          tags=["general"],
          summary="Search events by one or more filters",
          description="Returns a list of events based on event's name, price, ticket type, start/end date, etc...",)
def search_event(search_params: Annotated[EventSearch, Body(
    title="Search Body",
    description="Combine one or more search parameters to find events."
)]):
    search_params_dict = search_params.dict(exclude_unset=True)
    pandas_params = parse_params(df, search_params_dict)
    return df[pandas_params].replace([np.nan], None).to_dict("records")


if __name__ == "__main__":
    from argparse import ArgumentParser
    parser = ArgumentParser(prog='server')
    parser.add_argument('--host', default="127.0.0.1")
    parser.add_argument('--log_level', default="info")
    parser.add_argument('--port', default=8000, type=int)
    parser.add_argument('--use_ngrok', action='store_true')
    parser.add_argument('--ngrok_auth', required='--use_ngrok' in sys.argv, help="ngrok authentication token, required if --use_ngrok is set to True")
    args = parser.parse_args()

    if args.use_ngrok:
        from pyngrok import ngrok, conf
        from os import path
        pyngrok_config = conf.get_default()
        pyngrok_config.auth_token = args.ngrok_auth

        if not path.exists(pyngrok_config.ngrok_path):
            # Install ngrok
            from pyngrok import installer
            import ssl
            myssl = ssl.create_default_context()
            myssl.check_hostname=False
            myssl.verify_mode=ssl.CERT_NONE
            installer.install_ngrok(pyngrok_config.ngrok_path, context=myssl)

        public_url=ngrok.connect(args.port).public_url
        text=f"🌎 ngrok tunnel {public_url} -> {args.host}:{args.port}"
        print(text)

    config = uvicorn.Config("server:app",
                            port=args.port,
                            log_level=args.log_level,
                            host=args.host)
    server = uvicorn.Server(config)
    server.run()
