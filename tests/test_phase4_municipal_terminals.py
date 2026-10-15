"""Official network terminal reports are review-only, not dead-end publication."""
import unittest
from scripts.audit_municipal_terminals import terminal_candidates

BOUNDARY={"type":"Polygon","coordinates":[[
    [144.89,-37.81],[144.91,-37.81],[144.91,-37.79],[144.89,-37.79],[144.89,-37.81]
]]}


def road(pfi,street,a,b,start,end,**extra):
    return {"type":"Feature","geometry":{"type":"LineString","coordinates":[a,b]},
        "properties":{"pfi":pfi,"ezi_road_name":street,"from_ufi":start,"to_ufi":end,
            "feature_type_code":"road","road_status":"O","vehicular_access":"1",
            "class_code":5,"left_locality":"FOOTSCRAY","right_locality":"FOOTSCRAY",**extra}}


class SourceTerminalTests(unittest.TestCase):
    def test_degree_one_official_terminal_requires_independent_field_verification(self):
        a=[144.900,-37.800];b=[144.901,-37.800]
        doc={"type":"FeatureCollection","features":[
            road(11,"A STREET",a,b,100,101),
            road(12,"CROSS STREET",[144.901,-37.801],b,102,101),
            road(13,"CROSS STREET",b,[144.901,-37.799],101,103)]}
        items,report=terminal_candidates(doc,BOUNDARY,"roadsha","lgasha")
        candidate=next(x for x in items if x["sourcePFI"]=="11")
        self.assertEqual(candidate["terminalUFI"],"100")
        self.assertEqual(candidate["status"],"PENDING_FIELD_CONFIRMATION")
        self.assertFalse(candidate["physicalDeadEndVerified"])
        self.assertFalse(report["networkEndpointAloneEstablishesDeadEnd"])
        self.assertFalse(report["publicationApproved"])

    def test_official_reviewed_terminal_reference_is_separately_identified(self):
        a=[144.900,-37.800];b=[144.901,-37.800]
        doc={"type":"FeatureCollection","features":[road(11,"A STREET",a,b,100,101)]}
        rows,_=terminal_candidates(doc,BOUNDARY,"r","l",{"11"})
        self.assertEqual(len(rows),2)
        self.assertTrue(all(x["physicalDeadEndVerified"] for x in rows))

    def test_terminal_excludes_nonoperational_and_outside(self):
        src={"type":"FeatureCollection","features":[
            road(11,"A STREET",[144.90,-37.80],[144.901,-37.80],100,101,road_status="P"),
            road(12,"B STREET",[144.94,-37.80],[144.95,-37.80],110,111)]}
        rows,_=terminal_candidates(src,BOUNDARY,"r","l")
        self.assertEqual(rows,[])


if __name__=="__main__":
    unittest.main()
