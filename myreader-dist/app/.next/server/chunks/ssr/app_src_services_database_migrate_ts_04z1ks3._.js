module.exports=[760722,a=>{"use strict";async function b(a,c,d={}){let e=c.length;if(0===e)return;let f=await a.select("PRAGMA user_version");if((f[0]?.user_version??0)>=e)return;let g=d.table??"__migrations";await a.execute(`CREATE TABLE IF NOT EXISTS ${g} (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL UNIQUE,
      applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )`);let h=new Set((await a.select(`SELECT name FROM ${g}`)).map(a=>a.name));for(let b=0;b<c.length;b++){let d=c[b];if(h.has(d.name))continue;let e=d.sql.split(";").map(a=>a.trim()).filter(a=>a.length>0),f=d.name.replace(/'/g,"''");e.push(`INSERT INTO ${g} (name) VALUES ('${f}')`),e.push(`PRAGMA user_version = ${b+1}`),await a.batch(e)}}a.s(["migrate",0,b])}];

//# sourceMappingURL=app_src_services_database_migrate_ts_04z1ks3._.js.map