// 管理页角色守卫（r29）：/admin/* 只允许管理员进入。
// 页面 HTML 由后端 SpaStaticHandler 直出、不经过 BaseHandler，读者能拿到 200 的空壳页；
// 这里在路由层补一道，避免读者进设置页后因接口 403 缺字段而抛 TypeError。
// 注意：必须排在 require-login 之后（先判登录，再判角色）。
export default function ({ store, route, redirect }) {
  if (process.server) return; // 纯客户端项目（--spa），构建期不跑守卫
  if (!route.path.startsWith("/admin")) {
    return;
  }
  const user = (store.state && store.state.user) || {};
  if (!user.is_admin) {
    redirect("/");
  }
}
