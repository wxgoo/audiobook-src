// 密码强度与出生年份校验（4.6.0-19 r11）
//
// 规则与后端 webserver/models.py 的 Reader.check_password_strength /
// Reader.parse_birth_year 一一对应。前端做提示只是为了「边输边看到问题」，
// 后端仍会再校验一次（不信任前端）。
//
// 为什么单独抽出来：注册页、账号设置、管理员改密/建号四个地方都要用，
// 各写一份必然漂移（这套代码里已经有过教训，见交接单 B-1）。

export const PASSWORD_MIN_LEN = 6;
export const PASSWORD_MAX_LEN = 20;
// 大写 / 小写 / 数字 / 特殊符号，至少命中其中 N 类
export const PASSWORD_MIN_KINDS = 2;

// r11 起存出生年份而不是整数岁：年龄随时在变，存死了就会「注册时 12 岁，
// 三年后还是 12 岁」，分组限额永远不升级。出生年份下限 1900，上限当年年份
// （与后端 Reader.BIRTH_YEAR_MIN / current_year() 对齐）。
export const BIRTH_YEAR_MIN = 1900;

export function currentYear() {
    return new Date().getFullYear();
}

// 旧字段兼容：整数岁 → 出生年份
export function ageToBirthYear(age) {
    const n = Number(age);
    if (!Number.isFinite(n) || n <= 0) return 0;
    return currentYear() - Math.floor(n);
}

const KIND_TESTS = [
    { key: 'lower', re: /[a-z]/ },
    { key: 'upper', re: /[A-Z]/ },
    { key: 'digit', re: /[0-9]/ },
    { key: 'special', re: /[!@#$%^&*()_+\-=[\]{};':",./<>?\\|]/ },
];
// 与后端 RE_PASSWORD 白名单一致：只允许常见可见字符，挡掉空格/中文/emoji
const ALLOWED_RE = /^[a-zA-Z0-9!@#$%^&*()_+\-=[\]{};':",./<>?\\|]*$/;

// 返回命中的字符类别数（0~4），供「已满足几种」提示使用
export function passwordKinds(password) {
    const pwd = password || '';
    return KIND_TESTS.filter((k) => k.re.test(pwd)).length;
}

// 返回 null 表示通过，否则返回中文错误文案
export function checkPassword(password, t) {
    const msg = (key, fallback) => (t ? t(key) : fallback);
    const pwd = password || '';
    if (pwd.length < PASSWORD_MIN_LEN) {
        return msg('signup.pwdTooShort', `密码不能少于${PASSWORD_MIN_LEN}位`);
    }
    if (pwd.length > PASSWORD_MAX_LEN) {
        return msg('signup.pwdTooLong', `密码不能超过${PASSWORD_MAX_LEN}位`);
    }
    if (!ALLOWED_RE.test(pwd)) {
        return msg('signup.pwdBadChar', '密码只能包含字母、数字和常见符号');
    }
    if (passwordKinds(pwd) < PASSWORD_MIN_KINDS) {
        return msg('signup.pwdTooWeak', `密码太简单：需包含大写字母、小写字母、数字、符号中的至少${PASSWORD_MIN_KINDS}种`);
    }
    return null;
}

// 给 v-text-field 用的 rules 工厂
export function passwordRules(t) {
    return [
        (v) => checkPassword(v, t) || true,
    ];
}

// 返回 null 表示通过，否则返回错误文案。注册页、管理员改年龄共用。
export function checkBirthYear(value, t) {
    const msg = (key, fallback) => (t ? t(key) : fallback);
    const text = String(value === undefined || value === null ? '' : value).trim();
    if (!text) return msg('signup.birthYearRequired', '请填写出生年份');
    if (!/^\d{4}$/.test(text)) {
        return msg('signup.birthYearInvalid', '出生年份需为四位数字（如 1998）');
    }
    const n = Number(text);
    const hi = currentYear();
    if (n < BIRTH_YEAR_MIN || n > hi) {
        return msg('signup.birthYearRange', `出生年份需在${BIRTH_YEAR_MIN}~${hi}之间`);
    }
    return null;
}

export function birthYearRules(t) {
    return [
        (v) => checkBirthYear(v, t) || true,
    ];
}

// 由出生年份算年龄，用于管理员列表展示与「当前年龄」提示
export function ageFromBirthYear(birthYear) {
    const n = Number(birthYear);
    if (!Number.isFinite(n) || n <= 0) return 0;
    const age = currentYear() - Math.floor(n);
    return age > 0 ? age : 0;
}
