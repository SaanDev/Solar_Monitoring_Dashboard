from datetime import datetime

from pydantic import BaseModel


class F107Point(BaseModel):
    time: datetime
    flux: float       # F10.7 cm solar radio flux (sfu)


class F107Response(BaseModel):
    source: str = "noaa-swpc"
    data: list[F107Point]
