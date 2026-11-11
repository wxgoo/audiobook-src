<template>
  <div class="pl-6 mt-4">
    <div class="d-flex align-center reader-group-header" @click="toggle">
      <v-icon class="mr-2">mdi-account-lock-outline</v-icon>
      <span class="text-body-1">{{ $t("settings.reader_groups") }}</span>
      <v-icon class="ml-1">{{ expanded ? "mdi-chevron-down" : "mdi-chevron-right" }}</v-icon>
    </div>
    <div class="text-caption grey--text ml-8">{{ $t("settings.reader_groups_tips") }}</div>
    <v-expand-transition>
    <div v-show="expanded" class="pl-8">
      <!-- 预置模板：空白表格最劝退，给几套开箱即用的配置一键填充 -->
      <div class="d-flex align-center flex-wrap mt-3 mb-1">
        <v-menu offset-y>
          <template v-slot:activator="{ on, attrs }">
            <v-btn small outlined color="primary" v-bind="attrs" v-on="on">
              <v-icon left small>mdi-file-star-outline</v-icon>{{ $t("settings.reader_group_from_preset") }}
            </v-btn>
          </template>
          <v-list dense class="reader-group-preset-list">
            <template v-for="(sec, si) in presetSections">
              <v-subheader :key="'sh-' + si" class="text-caption font-weight-bold">
                {{ sec.group }}
              </v-subheader>
              <v-list-item v-for="p in sec.items" :key="p.name" @click="applyPreset(p)">
                <v-list-item-content>
                  <v-list-item-title>{{ p.name }}</v-list-item-title>
                  <v-list-item-subtitle class="text-caption">{{ p.desc }}</v-list-item-subtitle>
                </v-list-item-content>
              </v-list-item>
            </template>
          </v-list>
        </v-menu>
        <span class="text-caption grey--text ml-3">{{ $t("settings.reader_group_preset_tips") }}</span>
      </div>

      <!-- 新建/编辑组 -->
      <v-row dense class="mt-2">
        <v-col cols="12" sm="3">
          <v-text-field v-model="form.name" :label="$t('settings.reader_group_name')" dense hide-details outlined></v-text-field>
        </v-col>
        <v-col cols="12" sm="3">
          <v-select v-model="form.mode" :items="modeItems" :label="$t('settings.reader_group_mode')" dense hide-details outlined></v-select>
        </v-col>
        <v-col cols="12" sm="3">
          <v-combobox
            v-model="formCategories"
            :items="categoryOptions"
            :label="$t('settings.reader_group_categories')"
            :hint="$t('settings.reader_group_pick_hint')"
            :disabled="form.mode === 'open'"
            persistent-hint
            multiple
            chips
            small-chips
            deletable-chips
            clearable
            dense
            outlined
            hide-selected
          ></v-combobox>
        </v-col>
        <v-col cols="12" sm="3">
          <v-combobox
            v-model="formTags"
            :items="tagOptions"
            :label="$t('settings.reader_group_tags')"
            :hint="$t('settings.reader_group_pick_hint')"
            :disabled="form.mode === 'open'"
            persistent-hint
            multiple
            chips
            small-chips
            deletable-chips
            clearable
            dense
            outlined
            hide-selected
          ></v-combobox>
        </v-col>
      </v-row>
      <div class="text-caption grey--text">{{ $t("settings.reader_group_rule_tips") }}</div>
      <div class="text-caption grey--text">{{ $t("settings.reader_group_logic_tips") }}</div>
      <!-- 模板与本库标签对不上：白名单组「填了也看不到书」的头号原因 -->
      <div v-if="presetMiss && presetMiss.missing" class="text-caption mt-1">
        <span :class="presetMiss.mismatch ? 'orange--text' : 'grey--text'">
          <v-icon x-small :color="presetMiss.mismatch ? 'orange' : 'grey'">mdi-magnify</v-icon>
          {{ $t("settings.reader_group_preset_miss", {
            n: presetMiss.missing, total: presetMiss.total,
            list: presetMiss.list.slice(0, 12).join("、") + (presetMiss.list.length > 12 ? "…" : ""),
          }) }}
        </span>
        <v-btn x-small text color="primary" class="ml-1" @click="dropMissingFromPreset">
          {{ $t("settings.reader_group_preset_drop", { n: presetMiss.missing }) }}
        </v-btn>
        <div v-if="presetMiss.mismatch" class="orange--text">
          {{ $t("settings.reader_group_preset_mismatch") }}
        </div>
      </div>
      <!-- 白名单+空条件会「一本书都看不到」，这是最容易踩的坑，动态提醒一下 -->
      <div v-if="isEmptyWhitelist" class="text-caption orange--text mt-1">
        <v-icon x-small color="orange">mdi-alert-outline</v-icon>
        {{ $t("settings.reader_group_strict_tips") }}
      </div>
      <!-- 「不限」是唯一能表达「这组不受限制」的模式，条件输入已禁用，这里说明原因 -->
      <div v-if="form.mode === 'open'" class="text-caption success--text mt-1">
        <v-icon x-small color="success">mdi-lock-open-variant</v-icon>
        {{ $t("settings.reader_group_open_tips") }}
      </div>
      <v-btn color="primary" class="mt-2" :loading="saving" @click="saveGroup">
        <v-icon left>mdi-content-save</v-icon>{{ editing ? $t("settings.update") : $t("settings.add") }}
      </v-btn>
      <v-btn v-if="editing" text class="mt-2 ml-2" @click="resetForm">{{ $t("settings.cancel") }}</v-btn>

      <v-divider class="my-4"></v-divider>

      <!-- 组列表 -->
      <!-- 悬空引用：成员还挂着某个已删除的组名，这些人在权限上「读不到任何书」，
           不显式提示的话管理员完全无从发现（只会觉得"这人怎么啥都看不到"）。 -->
      <v-alert
        v-if="orphanNames.length"
        type="warning"
        dense
        outlined
        class="mb-3"
      >
        <div class="font-weight-medium mb-1">{{ $t("settings.reader_group_orphan_title") }}</div>
        <div
          v-for="g in orphanNames"
          :key="g"
          class="d-flex align-center flex-wrap text-caption"
        >
          <span class="mr-2">「{{ g }}」→ {{ orphans[g].join("、") }}</span>
          <v-btn
            x-small
            text
            color="warning"
            class="ml-1"
            :loading="reviving === g"
            :disabled="!!reviving"
            @click="revive([g])"
          >{{ $t("settings.reader_group_revive_one") }}</v-btn>
        </div>
        <div class="text-caption mt-1">{{ $t("settings.reader_group_orphan_tips") }}</div>
        <div class="mt-2">
          <v-btn
            x-small
            color="warning"
            outlined
            :loading="reviving === '*'"
            :disabled="!!reviving"
            @click="revive(null)"
          >
            <v-icon left x-small>mdi-auto-fix</v-icon>
            {{ $t("settings.reader_group_revive_all", { n: orphanNames.length }) }}
          </v-btn>
          <span class="text-caption grey--text ml-2">{{ $t("settings.reader_group_revive_hint") }}</span>
        </div>
      </v-alert>
      <div v-if="!loaded && loading" class="text-center py-4"><v-progress-circular indeterminate></v-progress-circular></div>
      <!-- 请求迟迟不回时不能一直转圈：显式报错并给重试入口，否则用户只能干等 -->
      <div v-else-if="loadError" class="text-caption error--text py-2">
        <v-icon x-small color="error">mdi-alert-circle-outline</v-icon>
        {{ loadError }}
        <v-btn x-small text color="primary" class="ml-1" @click="reload">{{ $t("settings.reader_group_retry") }}</v-btn>
      </div>
      <v-simple-table v-else-if="groupNames.length" dense>
        <thead>
          <tr>
            <th>{{ $t("settings.reader_group_name") }}</th>
            <th>{{ $t("settings.reader_group_mode") }}</th>
            <th>{{ $t("settings.reader_group_categories") }}</th>
            <th>{{ $t("settings.reader_group_tags") }}</th>
            <th>{{ $t("settings.reader_group_members") }}</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="name in groupNames" :key="name">
            <td>{{ name }}</td>
            <td>{{ modeText(groups[name].mode) }}</td>
            <td>{{ groups[name].categories || "-" }}</td>
            <td>{{ groups[name].tags || "-" }}</td>
            <td>{{ (groups[name].members || []).join(", ") || "-" }}</td>
            <td class="text-right">
              <v-btn icon small @click="editGroup(name)"><v-icon>mdi-pencil</v-icon></v-btn>
              <v-btn icon small @click="removeGroup(name)"><v-icon>mdi-delete</v-icon></v-btn>
            </td>
          </tr>
        </tbody>
      </v-simple-table>
      <div v-else class="text-caption grey--text">{{ $t("settings.reader_group_empty") }}</div>

      <v-divider class="my-4"></v-divider>

      <!-- 批量分配 -->
      <div class="text-body-2 mb-1">{{ $t("settings.reader_group_assign") }}</div>
      <v-row dense align="center">
        <v-col cols="12" sm="5">
          <v-select v-model="assignGroup" :items="groupNames" :label="$t('settings.reader_group_name')" dense hide-details outlined clearable></v-select>
        </v-col>
        <v-col cols="12" sm="5">
          <v-combobox
            v-model="assignUsers"
            :items="userOptions"
            :label="$t('settings.reader_group_usernames')"
            :hint="$t('settings.reader_group_usernames_hint')"
            persistent-hint
            multiple
            chips
            small-chips
            deletable-chips
            dense
            outlined
          ></v-combobox>
        </v-col>
        <v-col cols="12" sm="2">
          <v-btn color="primary" block :loading="assigning" :disabled="!assignUsers || !assignUsers.length" @click="assign">
            <v-icon left>mdi-account-multiple-check</v-icon>{{ $t("settings.reader_group_assign_btn") }}
          </v-btn>
        </v-col>
      </v-row>
      <div class="text-caption grey--text">{{ $t("settings.reader_group_assign_tips") }}</div>
    </div>
    </v-expand-transition>
  </div>
</template>

<script>
// 读者组分级权限编辑器（移植自 audiobook 的按年级分组限读）。
// 自包含：挂载后自行读写 /api/admin/reader_groups*，不经过设置页的统一保存。
export default {
  name: "ReaderGroupEditor",
  data: () => ({
    expanded: false,
    loaded: false,
    loading: false,
    // 加载失败/超时的提示文案（空串表示没有错误）
    loadError: "",
    saving: false,
    assigning: false,
    // 正在重建的悬空组名；'*' 表示「全部重建」。非空时按钮统一禁用，
    // 避免连点造成重复建组。
    reviving: "",
    groups: {},
    // 悬空引用：{组名: [用户名]}，成员的组已被删/改名，导致这些人权限判定为
    // 「组不存在 → 读不到任何书」，需要在界面上显式提示重新分配。
    orphans: {},
    form: { name: "", mode: "whitelist", categories: "", tags: "", old_name: "" },
    editing: false,
    // 候选值：从系统里实际存在的分类/标签拉取，供 v-combobox 下拉选择。
    // 仍允许自由输入（combo 而非 select），避免新分类还没入库时无法预先填。
    categoryOptions: [],
    tagOptions: [],
    optionsLoaded: false,
    presets: [],
    assignGroup: "",
    assignUsers: [],
    // 用户名候选：来自 options 接口（数据库里真实存在的读者），
    // combobox 仍允许自由输入，兼容还没建账号的预分配场景。
    userOptions: [],
  }),
  computed: {
    // 白名单 + 分类标签都为空 = 严格模式下成员一本书都看不到，表单里提前警示
    isEmptyWhitelist() {
      const f = this.form || {};
      if (f.mode !== "whitelist") return false;
      // 后端存的是逗号分隔字符串，这里不能假设是数组
      return this.splitList(f.categories).length === 0
        && this.splitList(f.tags).length === 0;
    },
    modeItems() {
      return [
        { text: this.$t("settings.reader_group_mode_whitelist"), value: "whitelist" },
        { text: this.$t("settings.reader_group_mode_blacklist"), value: "blacklist" },
        { text: this.$t("settings.reader_group_mode_open"), value: "open" },
      ];
    },
    groupNames() {
      return Object.keys(this.groups).sort();
    },
    orphanNames() {
      return Object.keys(this.orphans || {}).sort();
    },
    // form.categories / form.tags 后端存的是逗号分隔字符串，v-combobox multiple
    // 需要数组。这里用 getter/setter 做双向转换，提交时再 join 回字符串，
    // 保证与后端已有格式（_normalize_tags 也接受 list）完全兼容。
    formCategories: {
      get() {
        return this.splitList(this.form.categories);
      },
      set(val) {
        this.form.categories = this.joinList(val);
      },
    },
    formTags: {
      get() {
        return this.splitList(this.form.tags);
      },
      set(val) {
        this.form.tags = this.joinList(val);
      },
    },
    // 模板与当前书库的匹配度：模板里的标签/分类有多少在本库真实存在。
    // 模板照着一套通用书库写，换个库很可能大半对不上——白名单组只认真实存在
    // 的标签，对不上就等于「填了也看不到书」，界面上必须说清。
    // options 还没拉到时返回 null，免得把「没加载完」误报成「全部未命中」。
    presetMiss() {
      if (!this.optionsLoaded) return null;
      const tags = this.splitList(this.form.tags);
      const cats = this.splitList(this.form.categories);
      const total = tags.length + cats.length;
      if (!total) return null;
      const tset = new Set(this.tagOptions);
      const cset = new Set(this.categoryOptions);
      const missTags = tags.filter((t) => !tset.has(t));
      const missCats = cats.filter((c) => !cset.has(c));
      const missing = missTags.length + missCats.length;
      return {
        tags: missTags,
        cats: missCats,
        total,
        missing,
        mismatch: missing / total >= 0.5,
        list: missCats.concat(missTags),
      };
    },
    // 模板按「给谁用 / 读什么」分栏：十几套平铺一列找起来费劲。
    // 分栏顺序按后端返回的先后，不在前端硬编码名单——加模板只改后端。
    presetSections() {
      const out = [];
      const idx = {};
      for (const p of this.presets) {
        const g = p.group || "";
        if (idx[g] === undefined) {
          idx[g] = out.length;
          out.push({ group: g, items: [] });
        }
        out[idx[g]].items.push(p);
      }
      return out;
    },
  },
  methods: {
    // 组列表里的模式列：三态映射，别再写成二元三元表达式。
    // 注意必须放在 methods：模板里是 modeText(groups[name].mode) 带参调用，
    // 放进 computed 会被 Vue 无参求值成字符串，再调用就抛
    // “modeText is not a function”，整个组件渲染中断、列表停在转圈。
    modeText(mode) {
      if (mode === "open") return this.$t("settings.reader_group_mode_open");
      return this.$t(
        mode === "blacklist"
          ? "settings.reader_group_mode_blacklist"
          : "settings.reader_group_mode_whitelist"
      );
    },
    // ---------- 列表字符串 <-> 数组 ----------
    splitList(value) {
      const parts = Array.isArray(value)
        ? value
        : String(value || "").split(",");
      // 去空 + 去重：历史数据里可能有重复项，直接塞进 chips 会出现重复标签
      const seen = new Set();
      const out = [];
      for (const raw of parts) {
        const s = String(raw || "").trim();
        if (s && !seen.has(s)) {
          seen.add(s);
          out.push(s);
        }
      }
      return out;
    },
    joinList(value) {
      if (!Array.isArray(value)) return String(value || "").trim();
      // 去空、去重（后端 _normalize_tags 也会去重，这里先处理让 UI 更干净）
      const seen = new Set();
      const out = [];
      for (const raw of value) {
        const s = String(raw || "").trim();
        if (s && !seen.has(s)) {
          seen.add(s);
          out.push(s);
        }
      }
      return out.join(",");
    },
    async loadOptions() {
      if (this.optionsLoaded) return;
      try {
        const rsp = await this.$backend("/admin/reader_groups/options");
        if (rsp.err === "ok") {
          this.categoryOptions = rsp.categories || [];
          this.tagOptions = rsp.tags || [];
          this.userOptions = rsp.usernames || [];
          this.optionsLoaded = true;
        }
      } catch (err) {
        // 拿不到候选值不影响使用：combobox 仍可自由输入
        console.error("load reader group options failed:", err);
      }
    },
    async loadPresets() {
      if (this.presets.length) return;
      try {
        const rsp = await this.$backend("/admin/reader_groups/presets");
        if (rsp.err === "ok") this.presets = rsp.presets || [];
      } catch (err) {
        // 模板拉不到就只保留手填，不影响主流程
        console.error("load reader group presets failed:", err);
      }
    },
    // 模板只填表单，不直接落库 —— 管理员可以先改再保存，
    // 避免点一下就在后台凭空多出一个组。
    async applyPreset(p) {
      this.form = {
        name: p.name || "",
        mode: p.mode || "whitelist",
        categories: p.categories || "",
        tags: p.tags || "",
        old_name: "",
      };
      this.editing = false;
      // 载入模板后要立刻算「本库命中多少」，候选值没拉到就先拉一次
      await this.loadOptions();
    },
    // 去掉模板里本库不存在的标签/分类：白名单组看不到书时，第一个要排查的
    // 就是「标签名对不上」，与其让管理员逐条比对，不如一键清掉再按需补。
    dropMissingFromPreset() {
      const miss = this.presetMiss;
      if (!miss) return;
      const tset = new Set(miss.tags);
      const cset = new Set(miss.cats);
      this.form.categories = this.splitList(this.form.categories)
        .filter((c) => !cset.has(c)).join(",");
      this.form.tags = this.splitList(this.form.tags)
        .filter((t) => !tset.has(t)).join(",");
    },
    toggle() {
      this.expanded = !this.expanded;
      if (this.expanded) {
        this.reload();
        this.loadOptions();
        this.loadPresets();
      }
    },
    async reload() {
      this.loading = true;
      this.loadError = "";
      // 请求可能落在服务启动/重启的窗口里：$backend 对 server_starting 会返回
      // 一个永不 settle 的 Promise（上层另有整页跳 /starting 的兜底），这里再加
      // 一道保险——超时就把转圈停掉，别让页面停在「什么都不说」的状态。
      let timer = null;
      try {
        const rsp = await Promise.race([
          this.$backend("/admin/reader_groups"),
          new Promise((resolve) => {
            timer = setTimeout(() => resolve({ err: "timeout" }), 20000);
          }),
        ]);
        if (rsp.err === "ok") {
          this.groups = rsp.groups || {};
          this.orphans = rsp.orphans || {};
          this.loaded = true;
        } else if (rsp.err === "timeout") {
          this.loadError = this.$t("settings.reader_group_load_timeout");
        } else {
          this.$alert("error", rsp.msg || rsp.err);
          this.loadError = rsp.msg || rsp.err;
        }
      } catch (err) {
        this.$alert("error", String(err));
        this.loadError = String(err);
      }
      if (timer) {
        clearTimeout(timer);
      }
      this.loading = false;
    },
    resetForm() {
      this.form = { name: "", mode: "whitelist", categories: "", tags: "", old_name: "" };
      this.editing = false;
    },
    editGroup(name) {
      const g = this.groups[name] || {};
      this.form = {
        name,
        mode: g.mode || "whitelist",
        categories: g.categories || "",
        tags: g.tags || "",
        // 记住编辑前的组名：管理员改组名时后端按「改名」处理，
        // 迁移成员归属，否则成员会挂在旧组名下像被清空了一样
        old_name: name,
      };
      this.editing = true;
    },
    async saveGroup() {
      if (!this.form.name.trim()) {
        this.$alert("error", this.$t("settings.reader_group_name_required"));
        return;
      }
      this.saving = true;
      try {
        const rsp = await this.$backend("/admin/reader_groups", {
          method: "POST",
          body: JSON.stringify(this.form),
        });
        if (rsp.err === "ok") {
          this.groups = rsp.groups || {};
          this.orphans = rsp.orphans || {};
          this.$alert("success", this.$t("settings.saved"));
          this.resetForm();
        } else {
          this.$alert("error", rsp.msg || rsp.err);
        }
      } catch (err) {
        this.$alert("error", String(err));
      }
      this.saving = false;
    },
    async removeGroup(name) {
      if (!window.confirm(this.$t("settings.reader_group_confirm_delete", { name }))) return;
      try {
        const rsp = await this.$backend("/admin/reader_groups/delete", {
          method: "POST",
          body: JSON.stringify({ name }),
        });
        if (rsp.err === "ok") {
          await this.reload();
        } else {
          this.$alert("error", rsp.msg || rsp.err);
        }
      } catch (err) {
        this.$alert("error", String(err));
      }
    },
    // 按悬空组名重建空组：成员归属（Reader.extra.reader_group）一直都还在，
    // 组定义一回来这些人立刻归位，管理员只需补填白名单条件。
    // names 为 null 表示重建全部悬空组。
    async revive(names) {
      if (this.reviving) return;
      this.reviving = names ? names[0] : "*";
      try {
        const rsp = await this.$backend("/admin/reader_groups/revive", {
          method: "POST",
          body: JSON.stringify(names ? { names } : {}),
        });
        if (rsp.err === "ok") {
          this.groups = rsp.groups || {};
          this.orphans = rsp.orphans || {};
          this.$alert(
            "success",
            this.$t("settings.reader_group_revived", {
              n: (rsp.revived || []).length,
              names: (rsp.revived || []).join("、"),
            })
          );
        } else if (rsp.err === "nothing") {
          // 组已经重建过了（另一个标签页操作过 / 连点），刷新即可
          this.groups = rsp.groups || {};
          this.orphans = rsp.orphans || {};
          this.$alert("info", this.$t("settings.reader_group_revive_none"));
        } else {
          this.$alert("error", rsp.msg || rsp.err);
        }
      } catch (err) {
        this.$alert("error", String(err));
      }
      this.reviving = "";
    },
    async assign() {
      // chips 数组 + 手输残余项统一清洗：按逗号/分号/空白切分（手输 "alice bob"
      // 也要拆成两个用户），再 trim、去空、去重
      const raw = this.joinList(this.assignUsers);
      const seen = new Set();
      const usernames = [];
      for (const part of raw.split(/[,;\s]+/)) {
        const s = part.trim();
        if (s && !seen.has(s)) {
          seen.add(s);
          usernames.push(s);
        }
      }
      if (!usernames.length) return;
      this.assigning = true;
      try {
        const rsp = await this.$backend("/admin/reader_groups/assign", {
          method: "POST",
          body: JSON.stringify({ usernames, group: this.assignGroup || "" }),
        });
        if (rsp.err === "ok") {
          const missing = (rsp.missing || []).length;
          this.$alert(
            "success",
            this.$t("settings.reader_group_assigned", { n: rsp.assigned }) +
              (missing ? " " + this.$t("settings.reader_group_missing", { n: missing }) : "")
          );
          this.assignUsers = [];
          await this.reload();
        } else {
          this.$alert("error", rsp.msg || rsp.err);
        }
      } catch (err) {
        this.$alert("error", String(err));
      }
      this.assigning = false;
    },
  },
};
</script>

<style scoped>
.reader-group-header {
  cursor: pointer;
  user-select: none;
}
/* 模板十几套，菜单限高滚动，别撑出屏幕 */
.reader-group-preset-list {
  max-height: 70vh;
  max-width: 460px;
  overflow-y: auto;
  overflow-x: hidden;
}
.reader-group-preset-list .v-list__tile__sub-title {
  white-space: normal;
  line-height: 1.3;
}
</style>
