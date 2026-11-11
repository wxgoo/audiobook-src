#!/usr/bin/env node
/**
 * 静态扫描 Vue 单文件组件里“调用了不存在的成员”的写法。
 *
 * 背景：读者组的 modeText 与书列表页的 this.alert 都属于同一类问题——
 * 模板/脚本里写了一个组件上并不存在的函数，运行时抛 TypeError，被 Promise
 * 或 Vue 的错误处理吞掉，页面只剩下“空白/没反应”，控制台也很难看出来。
 *
 * 两类检查：
 *   1. <script> 中的 this.NAME(...)   —— 找不到定义即视为错误（--strict 时退出码 1）
 *   2. <template> 中的 NAME(...)      —— 只提示（模板里可能有 mixin/动态成员），不参与退出码
 *
 * 用法：
 *   node scripts/check-vue-method-refs.js            # 只报告
 *   node scripts/check-vue-method-refs.js --strict   # 有脚本级命中时退出 1
 */

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', 'src');
const strict = process.argv.includes('--strict');

// 组件上确实存在、但不需要在本文件里声明的成员（mixin、全局注入、Vue 内置）。
const SCRIPT_IGNORE = new Set([
  // Vue 内置
  '$emit', '$set', '$delete', '$nextTick', '$forceUpdate', '$watch', '$refs', '$el',
  '$options', '$parent', '$root', '$children', '$slots', '$scopedSlots', '$attrs',
  '$listeners', '$props', '$data', '$router', '$route', '$store', '$i18n', '$t',
  // 全局注入（plugins/*.js 用 inject 注册，不在组件内声明）
  '$backend', '$alert', '$sessionEpoch', '$resetSession',
  // vue-chartjs 的 mixin 提供 renderChart（不在组件内声明）
  'renderChart',
  // 生命周期 / 渲染钩子
  'created', 'mounted', 'destroyed', 'beforeDestroy', 'beforeMount', 'updated',
  'activated', 'deactivated', 'render', 'head', 'asyncData', 'fetch', 'validate',
  'beforeRouteEnter', 'beforeRouteUpdate', 'beforeRouteLeave', 'data', 'setup',
]);

const TEMPLATE_GLOBALS = new Set([
  'Math', 'JSON', 'Number', 'String', 'Boolean', 'Array', 'Object', 'Date', 'RegExp',
  'Promise', 'Set', 'Map', 'Error', 'parseInt', 'parseFloat', 'isNaN', 'isFinite',
  'encodeURIComponent', 'decodeURIComponent', 'encodeURI', 'decodeURI',
  'setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'console',
  'require', 'Intl', 'URL', 'URLSearchParams', 'Blob', 'FormData', 'FileReader',
  // 模板内联样式里常见的 CSS 函数，不是组件方法
  'calc', 'url', 'var', 'rgba', 'rgb', 'hsl', 'hsla', 'repeat', 'min', 'max',
  'clamp', 'env', 'attr', 'blur', 'translate', 'translateX', 'translateY',
  'scale', 'rotate', 'linear-gradient', 'radial-gradient', 'cubic-bezier', 'in',
]);

function walk(dir, out) {
  for (const name of fs.readdirSync(dir)) {
    const full = path.join(dir, name);
    const stat = fs.statSync(full);
    if (stat.isDirectory()) {
      walk(full, out);
    } else if (name.endsWith('.vue')) {
      out.push(full);
    }
  }
  return out;
}

// 从 start（指向 '{'）开始做花括号配对，返回结束下标。
function matchBrace(src, start) {
  let depth = 0;
  let quote = null;
  for (let i = start; i < src.length; i += 1) {
    const ch = src[i];
    if (quote) {
      if (ch === '\\') i += 1;
      else if (ch === quote) quote = null;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === '`') {
      quote = ch;
    } else if (ch === '{') {
      depth += 1;
    } else if (ch === '}') {
      depth -= 1;
      if (depth === 0) return i;
    }
  }
  return src.length;
}

// 收集 block（methods/computed/...）第一层的键名。
// 按行统计花括号深度：深度 0 的行首标识符就是第一层键（async foo() / foo: ... 都能认）。
function collectObjectKeys(src, keyName) {
  const keys = new Set();
  const re = new RegExp(`(?:^|[\\s,{])${keyName}\\s*:\\s*\\{`, 'g');
  let m;
  while ((m = re.exec(src)) !== null) {
    const brace = src.indexOf('{', m.index + m[0].length - 1);
    const end = matchBrace(src, brace);
    const body = src.slice(brace + 1, end);
    let depth = 0;
    for (const line of body.split('\n')) {
      const code = stripStringsAndComments(line);
      if (depth === 0) {
        const km = /^\s*(?:async\s+)?["']?([A-Za-z_$][\w$]*)["']?\s*[:(]/.exec(code);
        if (km) keys.add(km[1]);
        // 简写：methods: { toStars, fromStars }
        const sm = /^\s*([A-Za-z_$][\w$]*)\s*,?\s*$/.exec(code);
        if (sm) keys.add(sm[1]);
      }
      depth += countChar(code, '{') - countChar(code, '}');
      if (depth < 0) depth = 0;
    }
  }
  return keys;
}

function countChar(str, ch) {
  let n = 0;
  for (let i = 0; i < str.length; i += 1) {
    if (str[i] === ch) n += 1;
  }
  return n;
}

// 去掉行内字符串与注释，避免 "{" / "// }" 干扰深度统计。
function stripStringsAndComments(line) {
  return line
    .replace(/\/\/.*$/, '')
    .replace(/'(?:[^'\\]|\\.)*'/g, "''")
    .replace(/"(?:[^"\\]|\\.)*"/g, '""')
    .replace(/`(?:[^`\\]|\\.)*`/g, '``');
}

function collectDataKeys(src) {
  const keys = new Set();
  const re = /data\s*(?:\([^)]*\)|:)?\s*(?:=>\s*)?\{/g;
  let m;
  while ((m = re.exec(src)) !== null) {
    const brace = src.indexOf('{', m.index + m[0].length - 1);
    const end = matchBrace(src, brace);
    const body = src.slice(brace + 1, end);
    const ret = /return\s*\{/.exec(body);
    if (!ret) continue;
    const retBrace = body.indexOf('{', ret.index + ret[0].length - 1);
    const retEnd = matchBrace(body, retBrace);
    const inner = body.slice(retBrace + 1, retEnd);
    let depth = 0;
    for (const line of inner.split('\n')) {
      const code = stripStringsAndComments(line);
      if (depth === 0) {
        const km = /^\s*["']?([A-Za-z_$][\w$]*)["']?\s*:/.exec(code);
        if (km) keys.add(km[1]);
      }
      depth += countChar(code, '{') - countChar(code, '}');
      if (depth < 0) depth = 0;
    }
  }
  return keys;
}

function collectPropsKeys(src) {
  const keys = new Set();
  const arr = /props\s*:\s*\[([^\]]*)\]/.exec(src);
  if (arr) {
    const re = /["']([A-Za-z_$][\w$]*)["']/g;
    let m;
    while ((m = re.exec(arr[1])) !== null) keys.add(m[1]);
  }
  const obj = /props\s*:\s*\{/.exec(src);
  if (obj) {
    const brace = src.indexOf('{', obj.index + obj[0].length - 1);
    const end = matchBrace(src, brace);
    const body = src.slice(brace + 1, end);
    const re = /(?:^|[\s,{])["']?([A-Za-z_$][\w$]*)["']?\s*:/g;
    let m;
    while ((m = re.exec(body)) !== null) keys.add(m[1]);
  }
  return keys;
}

function collectInjectKeys(src) {
  const keys = new Set();
  const arr = /inject\s*:\s*\[([^\]]*)\]/.exec(src);
  if (arr) {
    const re = /["']([A-Za-z_$][\w$]*)["']/g;
    let m;
    while ((m = re.exec(arr[1])) !== null) keys.add(m[1]);
  }
  const obj = /inject\s*:\s*\{/.exec(src);
  if (obj) {
    const brace = src.indexOf('{', obj.index + obj[0].length - 1);
    const end = matchBrace(src, brace);
    const re = /(?:^|[\s,{])["']?([A-Za-z_$][\w$]*)["']?\s*:/g;
    let m;
    const body = src.slice(brace + 1, end);
    while ((m = re.exec(body)) !== null) keys.add(m[1]);
  }
  return keys;
}

// 运行时挂到实例上的成员，例如 this.unwatchLocale = this.$watch(...)
function collectRuntimeAssignments(src) {
  const names = new Set();
  const re = /this\.([A-Za-z_$][\w$]*)\s*=(?!=)/g;
  let m;
  while ((m = re.exec(src)) !== null) names.add(m[1]);
  return names;
}

function lineOf(src, index) {
  return src.slice(0, index).split('\n').length;
}

function scanFile(file) {
  const raw = fs.readFileSync(file, 'utf8');
  const scriptMatch = /<script[^>]*>([\s\S]*?)<\/script>/.exec(raw);
  const errors = [];
  const warnings = [];
  if (!scriptMatch) return { errors, warnings };
  const script = scriptMatch[1];

  const defined = new Set([
    ...collectObjectKeys(script, 'methods'),
    ...collectObjectKeys(script, 'computed'),
    ...collectDataKeys(script),
    ...collectPropsKeys(script),
    ...collectInjectKeys(script),
    ...collectRuntimeAssignments(script),
  ]);

  if (process.env.DEBUG_REFS) {
    console.error('[refs]', file, [...defined].sort().join(','));
  }

  const thisRe = /this\.([A-Za-z_$][\w$]*)\s*\(/g;
  let m;
  while ((m = thisRe.exec(script)) !== null) {
    const name = m[1];
    if (name.startsWith('$')) continue;
    if (SCRIPT_IGNORE.has(name)) continue;
    if (defined.has(name)) continue;
    errors.push({ file, line: lineOf(script, m.index), name, where: 'script' });
  }

  const tplMatch = /<template>([\s\S]*)<\/template>/.exec(raw);
  if (tplMatch) {
    const tpl = tplMatch[1];
    const expressions = [];
    let mm;
    const mustache = /\{\{([\s\S]*?)\}\}/g;
    while ((mm = mustache.exec(tpl)) !== null) expressions.push(mm[1]);
    const attr = /(?:@[\w.:-]+|v-on:[\w.:-]+|v-if|v-else-if|v-show|v-for|:[\w.:-]+)="([^"]*)"/g;
    while ((mm = attr.exec(tpl)) !== null) expressions.push(mm[1]);
    for (const expr of expressions) {
      const callRe = /(?:^|[^.\w$])([A-Za-z_$][\w$]*)\s*\(/g;
      let c;
      while ((c = callRe.exec(expr)) !== null) {
        const name = c[1];
        if (name.length < 2) continue;
        if (name.startsWith('$')) continue;
        if (TEMPLATE_GLOBALS.has(name) || SCRIPT_IGNORE.has(name)) continue;
        if (defined.has(name)) continue;
        if (name === 'function' || name === 'return' || name === 'if' || name === 'typeof') continue;
        warnings.push({ file, line: 0, name, where: 'template' });
      }
    }
  }

  return { errors, warnings };
}

const files = walk(ROOT, []);
let errorCount = 0;
let warningCount = 0;
const seenWarnings = new Set();

for (const file of files) {
  const { errors, warnings } = scanFile(file);
  for (const e of errors) {
    errorCount += 1;
    console.log(`ERROR ${path.relative(ROOT, e.file)}:${e.line}  this.${e.name}()`);
  }
  for (const w of warnings) {
    const key = `${w.file}:${w.name}`;
    if (seenWarnings.has(key)) continue;
    seenWarnings.add(key);
    warningCount += 1;
    console.log(`WARN  ${path.relative(ROOT, w.file)}  ${w.name}()  (模板引用，需人工确认是否 mixin)`);
  }
}

// ---------------------------------------------------------------------------
// 首屏取数审计：静态产物（nuxt generate --spa）里 asyncData 只在构建期执行，
// 运行时直接进入路由不会重跑。若页面只有 asyncData，或只在 $route 的 watch 里取数
// （缺 immediate 且没有生命周期兜底），首屏就永远不会发请求——ListBook 就是这么空白的。
// ---------------------------------------------------------------------------
const PAGES = path.join(ROOT, 'pages');
const FETCH_RE = /this\.init\s*\(|this\.fetch[A-Za-z_$]*\s*\(|this\.load[A-Za-z_$]*\s*\(|this\.get[A-Za-z_$]*\s*\(|this\.query[A-Za-z_$]*\s*\(|this\.poll\s*\(|this\.refresh\s*\(|this\.check[A-Za-z_$]*\s*\(|this\.verify\s*\(|\$backend/;
// 安装引导页：本身没有列表数据，asyncData 只用于判断跳转，允许只有服务端取数。
const FETCH_ALLOW = new Set(['pages/welcome.vue']);

function hookBodies(script) {
  const out = [];
  const re = /\b(created|mounted|activated)\s*\([^)]*\)\s*\{/g;
  let m;
  while ((m = re.exec(script)) !== null) {
    const brace = script.indexOf('{', m.index + m[0].length - 1);
    out.push(script.slice(brace + 1, matchBrace(script, brace)));
  }
  return out;
}

function routeWatchEntries(script) {
  const out = [];
  const re = /["']?\$route(?:\.[A-Za-z_$]+)*["']?\s*:\s*\{/g;
  let m;
  while ((m = re.exec(script)) !== null) {
    const brace = script.indexOf('{', m.index + m[0].length - 1);
    const end = matchBrace(script, brace);
    out.push(script.slice(brace + 1, end));
  }
  return out;
}

let fetchIssues = 0;
let pageCount = 0;
for (const file of files) {
  if (!file.startsWith(PAGES + path.sep)) continue;
  const rel = path.relative(ROOT, file).replace(/\\/g, '/');
  const raw = fs.readFileSync(file, 'utf8');
  const sm = /<script[^>]*>([\s\S]*?)<\/script>/.exec(raw);
  if (!sm) continue;
  // 仅 re-export 的薄壳（all.vue 等）继承被导出页面的行为，不单独判定
  if (!/\bexport\s+default\s*\{/.test(sm[1])) continue;
  pageCount += 1;

  const script = sm[1];
  const hasAsyncData = /\basyncData\s*\(/.test(script);
  const lifecycleFetch = hookBodies(script).some((body) => FETCH_RE.test(body));
  const badWatch = routeWatchEntries(script).filter(
    (entry) => FETCH_RE.test(entry) && !/immediate\s*:\s*true/.test(entry)
  );

  if (hasAsyncData && !lifecycleFetch && !FETCH_ALLOW.has(rel)) {
    fetchIssues += 1;
    console.log(`ERROR ${rel}  只有 asyncData 取数：静态产物下直接进入/强刷不会发请求（需 mounted/created 兜底）`);
  }
  if (badWatch.length) {
    fetchIssues += 1;
    console.log(`ERROR ${rel}  只在 $route watch 里取数且缺 immediate：首屏直入不会触发（需生命周期兜底）`);
  }
}

console.log(`\n首屏取数审计（pages，${pageCount} 个自有页面）：${fetchIssues} 处隐患。`);
console.log(`\n扫描 ${files.length} 个 .vue：${errorCount} 处脚本级错误，${warningCount} 处模板级待确认。`);
if (strict && (errorCount > 0 || fetchIssues > 0)) {
  process.exit(1);
}
