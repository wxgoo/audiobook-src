// 密码强度与年龄校验（4.6.0-19 r10）
//
// 规则与后端 webserver/models.py 的 Reader.check_password_strength /
// Reader.parse_age 一一对应。前端做提示只是为了「边输边看到问题」，
// 后端仍会再校验一次（不信任前端）。
//
// 为什么单独抽出来：注册页、账号设置、管理员改密/建号四个地方都要用，
// 各写一份必然漂移（这套代码里已经有过教训，见交接单 B-1）。

export const PASSWORD_MIN_LEN = 6;
export const PASSWORD_MAX_LEN = 20;
// 大写 / 小写 / 数字 / 特殊符号，至少命中其中 N 类
export const PASSWORD_MIN_KINDS = 2;

export const AGE_MIN = 1;
export const AGE_MAX = 120;

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

export function ageRules(t) {
    return [
        (v) => {
            const text = String(v === undefined || v === null ? '' : v).trim();
            if (!text) return t ? t('signup.ageRequired') : '请填写年龄';
            if (!/^\d+$/.test(text)) return t ? t('signup.ageInvalid') : '年龄需为整数';
            const n = Number(text);
            if (n < AGE_MIN || n > AGE_MAX) {
                return t ? t('signup.ageRange') : `年龄需在${AGE_MIN}~${AGE_MAX}之间`;
            }
            return true;
        },
    ];
}
