module.exports=[698197,e=>{"use strict";async function t(e,a,i={}){let n=a.length;if(0===n)return;let E=await e.select("PRAGMA user_version");if((E[0]?.user_version??0)>=n)return;let l=i.table??"__migrations";await e.execute(`CREATE TABLE IF NOT EXISTS ${l} (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL UNIQUE,
      applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )`);let s=new Set((await e.select(`SELECT name FROM ${l}`)).map(e=>e.name));for(let t=0;t<a.length;t++){let i=a[t];if(s.has(i.name))continue;let n=i.sql.split(";").map(e=>e.trim()).filter(e=>e.length>0),E=i.name.replace(/'/g,"''");n.push(`INSERT INTO ${l} (name) VALUES ('${E}')`),n.push(`PRAGMA user_version = ${t+1}`),await e.batch(n)}}e.s(["migrate",0,t])}];

//# sourceMappingURL=app_src_services_database_migrate_ts_0j702aa._.js.map