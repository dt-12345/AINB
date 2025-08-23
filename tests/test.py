import ainb
import ainb.graph

ainb.AINB.from_file("tests/data/ChuchuFire.action.root.ainb").save_json("tests/output")
ainb.AINB.from_file("tests/data/Alerted.actionseq.root.ainb").save_json("tests/output")
ainb.AINB.from_file("tests/data/Main.module.ainb").save_json("tests/output")
ainb.AINB.from_file("tests/data/Bird.action.fleetothesky.module.ainb").save_json("tests/output")
ainb.AINB.from_file("tests/data/DungeonBossRito.action.SpreadShootAttack.module.ainb").save_json("tests/output")
ainb.AINB.from_file("tests/data/Drake.sp.action.root.ainb").save_json("tests/output")

orig: ainb.AINB = ainb.AINB.from_file("tests/data/Drake.sp.action.root.ainb")
new: ainb.AINB = ainb.AINB.from_json_text(orig.to_json())

assert orig.as_dict() == new.as_dict(), "oops they don't match"

ainb.graph.graph_all_commands(ainb.AINB.from_file("tests/data/Drake.sp.action.root.ainb"), render=True, output_dir="tests/output")
ainb.graph.graph_all_commands(ainb.AINB.from_file("tests/data/DungeonBossRito.action.SpreadShootAttack.module.ainb"), render=True, output_dir="tests/output")
ainb.graph.graph_all_commands(ainb.AINB.from_file("tests/data/Main.module.ainb"), render=True, output_dir="tests/output")
ainb.graph.graph_all_commands(ainb.AINB.from_json("tests/output/SplPlayerMake.root.json"), render=True, output_dir="tests/output")