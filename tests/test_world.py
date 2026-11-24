from joppa_yard.world import DEFAULT_AGENTS, Agent, World, WorldError
import pytest


def test_default_agents_start_on_walkable_unshared_tiles():
    world = World()
    occupied = set()
    for agent in world.agents.values():
        tile = world.tile(agent.x, agent.y)
        assert tile is not None and tile.walkable
        assert agent.pos() not in occupied
        occupied.add(agent.pos())
    assert len(world.agents) == len(DEFAULT_AGENTS)


def test_cannot_walk_on_sea_or_off_the_map():
    world = World()
    # Silas starts at dock (2,2). West a few times reaches sea or edge.
    silas = world.agents["silas"]
    start = silas.pos()
    # From (2,2) west to (1,2) dock, west to (0,2) sea.
    assert world.move("silas", "west")["ok"] is True
    blocked = world.move("silas", "west")
    assert blocked["ok"] is False
    assert "sea" in blocked["reason"]
    assert world.agents["silas"].pos() != (0, 2)
    # North from the top pier should fail as edge or sea.
    world2 = World(agents=[Agent("solo", "Solo", 1, 1)])  # pier
    # north of (1,1) is (1,0) sea
    assert world2.move("solo", "north")["ok"] is False
    assert world2.agents["solo"].pos() == (1, 1)
    assert start != world.agents["silas"].pos()  # first west did move


def test_two_agents_cannot_share_a_tile():
    world = World(agents=[Agent("a", "A", 2, 5), Agent("b", "B", 3, 5)])
    # a at (2,5) moves east onto b at (3,5)
    bump = world.move("a", "east")
    assert bump["ok"] is False
    assert "already there" in bump["reason"]
    assert world.agents["a"].pos() == (2, 5)
    assert world.agents["b"].pos() == (3, 5)


def test_cannot_start_on_sea_or_on_an_occupied_tile():
    with pytest.raises(WorldError):
        World(agents=[Agent("drowned", "Drowned", 0, 0)])
    with pytest.raises(WorldError):
        World(agents=[Agent("a", "A", 2, 5), Agent("b", "B", 2, 5)])


def test_work_increments_inventory_and_trade_conserves_cargo():
    world = World(agents=[Agent("a", "A", 2, 2), Agent("b", "B", 3, 2)])
    worked = world.work("a")
    assert worked["ok"] is True
    item = worked["item"]
    assert world.cargo_total(item) == 1
    traded = world.trade("a", item, "b")
    assert traded["ok"] is True
    assert world.agents["a"].inventory.get(item, 0) == 0
    assert world.agents["b"].inventory[item] == 1
    assert world.cargo_total(item) == 1


def test_trade_fails_if_not_adjacent_or_missing_item():
    world = World(agents=[Agent("a", "A", 2, 2), Agent("b", "B", 5, 5)])
    world.work("a")
    item = next(iter(world.agents["a"].inventory))
    far = world.trade("a", item, "b")
    assert far["ok"] is False
    assert "adjacent" in far["reason"]
    assert world.cargo_total(item) == 1
    close = World(agents=[Agent("a", "A", 2, 2), Agent("b", "B", 3, 2)])
    missing = close.trade("a", "fish", "b")
    assert missing["ok"] is False
    assert close.cargo_total("fish") == 0


def test_talk_and_look_are_safe():
    world = World()
    said = world.talk("tamar", "  the market is open  ")
    assert said["ok"] is True
    assert world.agents["tamar"].last_line == "the market is open"
    assert world.talk("tamar", "   ")["ok"] is False
    seen = world.look("eli")
    assert seen["ok"] is True
    assert seen["tile"] == "square"
    assert isinstance(seen["nearby"], list)
