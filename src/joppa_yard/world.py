"""Original 8x8 docks yard. No third-party maps or assets."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

# S = sea (impassable), P = pier, D = dock, W = warehouse, M = market,
# I = inn, A = alley, G = gate, . = square.
MAP_ROWS: tuple[str, ...] = (
    "SSSSSSSS",
    "SPPPPGGS",
    "SDDDD.GS",
    "SWWW..IS",
    "SWWW.MIS",
    "S....AIS",
    "SGGGGGGS",
    "SSSSSSSS",
)

TILE_NAMES = {
    "S": "sea",
    "P": "pier",
    "D": "dock",
    "W": "warehouse",
    "M": "market",
    "I": "inn",
    "A": "alley",
    "G": "gate",
    ".": "square",
}

# Occupations that can "work" on a given tile and the crate they produce.
WORK_YIELDS = {
    "pier": "fish",
    "dock": "rope",
    "warehouse": "crate",
    "market": "coin",  # coin here is in-world cargo, not a blockchain token
    "inn": "bread",
    "alley": "scrap",
    "gate": "pass",
    "square": "rumor",
}

DIRS = {
    "north": (0, -1),
    "south": (0, 1),
    "east": (1, 0),
    "west": (-1, 0),
}


@dataclass(frozen=True)
class Tile:
    x: int
    y: int
    kind: str

    @property
    def name(self) -> str:
        return TILE_NAMES[self.kind]

    @property
    def walkable(self) -> bool:
        return self.kind != "S"


@dataclass
class Agent:
    agent_id: str
    display_name: str
    x: int
    y: int
    inventory: dict[str, int] = field(default_factory=dict)
    last_line: str = ""

    def pos(self) -> tuple[int, int]:
        return (self.x, self.y)


# Default starting marks on walkable tiles that do not overlap.
DEFAULT_AGENTS: tuple[tuple[str, str, int, int], ...] = (
    ("silas", "Silas", 2, 2),   # dock
    ("tamar", "Tamar", 5, 4),   # market
    ("eli", "Eli", 3, 5),       # square
)


class WorldError(ValueError):
    """A world rule was violated by the caller (not by a failed in-game action)."""


class World:
    def __init__(self, agents: Iterable[Agent] | None = None) -> None:
        self.tiles: dict[tuple[int, int], Tile] = {}
        for y, row in enumerate(MAP_ROWS):
            if len(row) != len(MAP_ROWS[0]):
                raise WorldError("map rows must be rectangular")
            for x, ch in enumerate(row):
                if ch not in TILE_NAMES:
                    raise WorldError(f"unknown tile {ch!r} at {x},{y}")
                self.tiles[(x, y)] = Tile(x, y, ch)
        self.width = len(MAP_ROWS[0])
        self.height = len(MAP_ROWS)
        self.agents: dict[str, Agent] = {}
        if agents is None:
            agents = [Agent(i, n, x, y) for i, n, x, y in DEFAULT_AGENTS]
        for agent in agents:
            self.add_agent(agent)

    def add_agent(self, agent: Agent) -> None:
        if agent.agent_id in self.agents:
            raise WorldError(f"duplicate agent {agent.agent_id}")
        tile = self.tiles.get(agent.pos())
        if tile is None or not tile.walkable:
            raise WorldError(f"{agent.agent_id} cannot start on {agent.pos()}")
        if self.occupant(agent.x, agent.y):
            raise WorldError(f"tile {agent.pos()} is already occupied")
        self.agents[agent.agent_id] = agent

    def occupant(self, x: int, y: int, *, except_id: str | None = None) -> Agent | None:
        for agent in self.agents.values():
            if agent.agent_id == except_id:
                continue
            if agent.x == x and agent.y == y:
                return agent
        return None

    def tile(self, x: int, y: int) -> Tile | None:
        return self.tiles.get((x, y))

    def move(self, agent_id: str, direction: str) -> dict:
        agent = self.agents[agent_id]
        if direction not in DIRS:
            return {"ok": False, "reason": f"unknown direction {direction!r}"}
        dx, dy = DIRS[direction]
        nx, ny = agent.x + dx, agent.y + dy
        dest = self.tile(nx, ny)
        if dest is None:
            return {"ok": False, "reason": "edge of the map"}
        if not dest.walkable:
            return {"ok": False, "reason": "sea is impassable"}
        blocker = self.occupant(nx, ny, except_id=agent_id)
        if blocker is not None:
            return {"ok": False, "reason": f"{blocker.display_name} is already there"}
        agent.x, agent.y = nx, ny
        return {"ok": True, "tile": dest.name, "x": nx, "y": ny}

    def work(self, agent_id: str) -> dict:
        agent = self.agents[agent_id]
        tile = self.tile(agent.x, agent.y)
        assert tile is not None
        item = WORK_YIELDS[tile.name]
        agent.inventory[item] = agent.inventory.get(item, 0) + 1
        return {"ok": True, "item": item, "count": agent.inventory[item], "tile": tile.name}

    def talk(self, agent_id: str, line: str) -> dict:
        agent = self.agents[agent_id]
        cleaned = " ".join(line.split())[:160]
        if not cleaned:
            return {"ok": False, "reason": "empty line"}
        agent.last_line = cleaned
        return {"ok": True, "line": cleaned}

    def trade(self, agent_id: str, item: str, target_id: str) -> dict:
        if agent_id == target_id:
            return {"ok": False, "reason": "cannot trade with yourself"}
        seller = self.agents.get(agent_id)
        buyer = self.agents.get(target_id)
        if seller is None or buyer is None:
            return {"ok": False, "reason": "unknown trader"}
        if abs(seller.x - buyer.x) + abs(seller.y - buyer.y) > 1:
            return {"ok": False, "reason": "not adjacent"}
        if seller.inventory.get(item, 0) < 1:
            return {"ok": False, "reason": f"no {item} to give"}
        seller.inventory[item] -= 1
        if seller.inventory[item] == 0:
            del seller.inventory[item]
        buyer.inventory[item] = buyer.inventory.get(item, 0) + 1
        return {
            "ok": True,
            "item": item,
            "from": agent_id,
            "to": target_id,
            "buyer_count": buyer.inventory[item],
        }

    def look(self, agent_id: str) -> dict:
        agent = self.agents[agent_id]
        here = self.tile(agent.x, agent.y)
        assert here is not None
        nearby = []
        for dx, dy in ((0, -1), (0, 1), (1, 0), (-1, 0)):
            t = self.tile(agent.x + dx, agent.y + dy)
            if t is None:
                continue
            other = self.occupant(t.x, t.y)
            nearby.append(
                {
                    "x": t.x,
                    "y": t.y,
                    "name": t.name,
                    "walkable": t.walkable,
                    "agent": None if other is None else other.display_name,
                }
            )
        return {"ok": True, "tile": here.name, "x": agent.x, "y": agent.y, "nearby": nearby}

    def cargo_total(self, item: str) -> int:
        return sum(a.inventory.get(item, 0) for a in self.agents.values())

    def observation(self, agent_id: str) -> dict:
        agent = self.agents[agent_id]
        looked = self.look(agent_id)
        others = [
            {
                "id": other.agent_id,
                "name": other.display_name,
                "x": other.x,
                "y": other.y,
                "adjacent": abs(other.x - agent.x) + abs(other.y - agent.y) == 1,
                "last_line": other.last_line,
            }
            for other in self.agents.values()
            if other.agent_id != agent_id
        ]
        return {
            "agent_id": agent.agent_id,
            "name": agent.display_name,
            "x": agent.x,
            "y": agent.y,
            "tile": looked["tile"],
            "inventory": dict(agent.inventory),
            "nearby": looked["nearby"],
            "others": others,
        }
