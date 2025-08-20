import ainb

ainb.AINB.from_file("tests/data/ChuchuFire.action.root.ainb").save_json("tests/output")
ainb.AINB.from_file("tests/data/Alerted.actionseq.root.ainb").save_json("tests/output")
ainb.AINB.from_file("tests/data/Main.module.ainb").save_json("tests/output")
ainb.AINB.from_file("tests/data/Bird.action.fleetothesky.module.ainb").save_json("tests/output")
ainb.AINB.from_file("tests/data/DungeonBossRito.action.SpreadShootAttack.module.ainb").save_json("tests/output")
ainb.AINB.from_file("tests/data/Drake.sp.action.root.ainb").save_json("tests/output")