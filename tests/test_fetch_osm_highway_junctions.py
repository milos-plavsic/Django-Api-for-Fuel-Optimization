from routing.management.commands.fetch_osm_highway_junctions import highways_from_ref


def test_highways_from_osm_ref():
    assert highways_from_ref("I 44; US 69") == {"I-44", "US-69"}
