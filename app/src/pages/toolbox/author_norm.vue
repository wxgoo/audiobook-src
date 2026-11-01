<template>
  <v-container fluid class="pa-4">
    <!-- 页头 -->
    <v-row class="mb-3" align="center">
      <v-col class="text-center">
        <span class="text-h5 font-weight-bold">{{ $t('authorNorm.title') }}</span>
      </v-col>
      <v-col cols="auto">
        <v-btn small color="error" @click="$router.go(-1)">
          <v-icon small left>mdi-close</v-icon>{{ $t('authorNorm.close') }}
        </v-btn>
      </v-col>
    </v-row>

    <v-row justify="center">
      <v-col cols="12" md="10" lg="9">
        <v-alert type="info" text dense class="mb-4">
          <div class="text-body-2">{{ $t('authorNorm.intro') }}</div>
          <div class="text-caption mt-1">{{ $t('authorNorm.intro2') }}</div>
        </v-alert>

        <v-tabs v-model="tab" background-color="transparent" grow class="mb-4">
          <v-tab>{{ $t('authorNorm.tabScan') }}</v-tab>
          <v-tab>{{ $t('authorNorm.tabAlias') }}</v-tab>
        </v-tabs>

        <!-- ═══════════ Tab 1：体检 ═══════════ -->
        <v-card v-if="tab === 0" rounded="xl" outlined class="pa-5">
          <div class="d-flex align-center flex-wrap" style="gap: 12px">
            <v-btn color="primary" :loading="scanning" @click="doScan">
              <v-icon small left>mdi-stethoscope</v-icon>
              {{ scanning ? $t('authorNorm.scanning') : $t('authorNorm.scanBtn') }}
            </v-btn>
            <span v-if="report" class="text-caption text--secondary">
              {{ $t('authorNorm.summary', {
                total: report.total,
                dup: report.duplicates.length,
                sus: report.suspects.length,
                dirty: report.dirty.length,
              }) }}
            </span>
          </div>
          <div class="text-caption text--secondary mt-2">{{ $t('authorNorm.scanHint') }}</div>
        </v-card>

        <div v-if="tab === 0 && report">
          <!-- 确定重复 -->
          <v-card v-if="report.duplicates.length" rounded="xl" outlined class="pa-4 mt-4 norm-dup">
            <div class="text-subtitle-1 font-weight-bold mb-2">
              <v-icon small color="success" class="mr-1">mdi-check-circle</v-icon>
              {{ $t('authorNorm.duplicates', { n: report.duplicates.length }) }}
            </div>
            <div v-for="d in report.duplicates" :key="'d' + d.key" class="mb-4">
              <div class="text-body-2 mb-1">
                {{ $t('authorNorm.canonicalIs') }}
                <strong class="success--text">{{ d.canonical }}</strong>
                <span class="text--secondary">（{{ $t('authorNorm.booksCount', { n: d.books }) }}）</span>
              </div>
              <v-chip v-for="v in d.variants" :key="v.name" small label class="ma-1"
                      :color="v.name === d.canonical ? 'green lighten-3' : 'grey lighten-3'">
                {{ v.name }} <span class="text--secondary ml-1">×{{ v.count }}</span>
              </v-chip>
              <div class="mt-2">
                <v-btn x-small text color="primary" @click="addRule(d.canonical, otherNames(d))">
                  <v-icon x-small left>mdi-plus</v-icon>{{ $t('authorNorm.addAliasRule') }}
                </v-btn>
              </div>
              <v-divider class="mt-2"></v-divider>
            </div>
          </v-card>

          <!-- 疑似重复 -->
          <v-card v-if="report.suspects.length" rounded="xl" outlined class="pa-4 mt-4 norm-sus">
            <div class="text-subtitle-1 font-weight-bold mb-2">
              <v-icon small color="warning" class="mr-1">mdi-help-circle</v-icon>
              {{ $t('authorNorm.suspects', { n: report.suspects.length }) }}
            </div>
            <div class="text-caption text--secondary mb-2">{{ $t('authorNorm.suspectsHint') }}</div>
            <div v-for="(s, i) in report.suspects" :key="'s' + i" class="mb-4">
              <div class="text-body-2 mb-1">
                {{ $t('authorNorm.maybeSame') }}
                <strong>{{ s.variants.map(v => v.name).join(' / ') }}</strong>
                <span class="text--secondary">（{{ $t('authorNorm.booksCount', { n: s.books }) }}）</span>
              </div>
              <v-chip v-for="v in s.variants" :key="v.name" small label class="ma-1 grey lighten-3">
                {{ v.name }} <span class="text--secondary ml-1">×{{ v.count }}</span>
              </v-chip>
              <div class="mt-2">
                <v-btn x-small text color="primary" @click="addRule(s.canonical, otherNames(s))">
                  <v-icon x-small left>mdi-plus</v-icon>{{ $t('authorNorm.addAliasRule') }}
                </v-btn>
              </div>
              <v-divider class="mt-2"></v-divider>
            </div>
          </v-card>

          <!-- 脏名候选 -->
          <v-card v-if="report.dirty.length" rounded="xl" outlined class="pa-4 mt-4 norm-dirty">
            <div class="text-subtitle-1 font-weight-bold mb-2">
              <v-icon small color="orange" class="mr-1">mdi-broom</v-icon>
              {{ $t('authorNorm.dirty', { n: report.dirty.length }) }}
            </div>
            <div class="text-caption text--secondary mb-2">{{ $t('authorNorm.dirtyHint') }}</div>
            <v-simple-table dense class="norm-table">
              <thead>
                <tr>
                  <th class="text-caption">{{ $t('authorNorm.colDirtyName') }}</th>
                  <th class="text-caption">{{ $t('authorNorm.colCleanName') }}</th>
                  <th class="text-caption">{{ $t('authorNorm.colBooks') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="d in report.dirty" :key="d.name">
                  <td class="text-caption">{{ d.name }}</td>
                  <td class="text-caption success--text">{{ d.clean }}</td>
                  <td class="text-caption">{{ d.count }}</td>
                </tr>
              </tbody>
            </v-simple-table>
            <div class="text-caption text--secondary mt-2">{{ $t('authorNorm.dirtyFooter') }}</div>
          </v-card>

          <!-- 空结果 -->
          <v-card v-if="scanned && !hasFindings" rounded="xl" outlined class="pa-8 mt-4 text-center">
            <v-icon size="56" color="success">mdi-check-decagram</v-icon>
            <div class="text-h6 mt-3">{{ $t('authorNorm.allClean') }}</div>
            <div class="text-caption text--secondary mt-1">{{ $t('authorNorm.allCleanHint') }}</div>
          </v-card>
        </div>

        <!-- ═══════════ Tab 2：别名表 ═══════════ -->
        <div v-if="tab === 1">
          <v-card rounded="xl" outlined class="pa-5">
            <div class="d-flex align-center flex-wrap" style="gap: 12px">
              <v-btn color="success" :loading="saving" @click="saveAlias">
                <v-icon small left>mdi-content-save</v-icon>{{ $t('authorNorm.saveBtn') }}
              </v-btn>
              <v-btn text @click="addRule('', [])">
                <v-icon small left>mdi-plus</v-icon>{{ $t('authorNorm.newRule') }}
              </v-btn>
              <span class="text-caption text--secondary">
                {{ $t('authorNorm.ruleCount', { n: aliasRules.length }) }}
              </span>
            </div>
            <div class="text-caption text--secondary mt-2">{{ $t('authorNorm.aliasHint') }}</div>
          </v-card>

          <!-- 规则列表 -->
          <v-card v-for="(r, i) in aliasRules" :key="'r' + i" rounded="xl" outlined class="pa-4 mt-3">
            <div class="d-flex align-center mb-2">
              <v-text-field v-model="r.name" dense hide-details outlined
                            :label="$t('authorNorm.colStandard')"
                            style="max-width: 320px" class="mr-3"></v-text-field>
              <v-text-field v-model="r.note" dense hide-details outlined
                            :label="$t('authorNorm.colNote')"
                            style="max-width: 240px"></v-text-field>
              <v-spacer></v-spacer>
              <v-btn icon small color="error" @click="aliasRules.splice(i, 1)">
                <v-icon small>mdi-delete</v-icon>
              </v-btn>
            </div>
            <div class="d-flex align-center flex-wrap" style="gap: 6px">
              <v-chip v-for="(a, j) in r.aliases" :key="j" close small label class="ma-1 grey lighten-3"
                      @click:close="r.aliases.splice(j, 1)">{{ a }}</v-chip>
              <v-text-field v-model="r._newAlias" dense hide-details outlined
                            :placeholder="$t('authorNorm.aliasPlaceholder')"
                            style="max-width: 220px; height: 40px"
                            @keydown.enter="commitAlias(r)"></v-text-field>
            </div>
          </v-card>

          <!-- 归一化预览 -->
          <v-card rounded="xl" outlined class="pa-5 mt-4">
            <div class="text-subtitle-1 font-weight-bold mb-2">{{ $t('authorNorm.testTitle') }}</div>
            <div class="d-flex align-center" style="gap: 12px">
              <v-text-field v-model="testName" dense hide-details outlined
                            :placeholder="$t('authorNorm.testPlaceholder')"
                            style="max-width: 360px"
                            @keydown.enter="doTest"></v-text-field>
              <v-btn color="primary" small :loading="testing" @click="doTest">
                <v-icon small left>mdi-flask</v-icon>{{ $t('authorNorm.testBtn') }}
              </v-btn>
            </div>
            <div v-if="testResult" class="mt-3">
              <v-alert :type="testResult.hit ? 'success' : 'info'" text dense class="mb-0">
                <div class="text-body-2">
                  {{ testResult.input }} →
                  <strong>{{ testResult.resolved }}</strong>
                  <span v-if="!testResult.hit" class="text--secondary">（{{ $t('authorNorm.testNoHit') }}）</span>
                </div>
                <div class="text-caption mt-1 text--secondary">
                  L1: {{ testResult.l1 }} · key: {{ testResult.norm_key }}
                  <template v-if="testResult.translators && testResult.translators.length">
                    · {{ $t('authorNorm.testTranslators') }}: {{ testResult.translators.join('、') }}
                  </template>
                </div>
              </v-alert>
            </div>
          </v-card>
        </div>
      </v-col>
    </v-row>

    <AppDialog
      v-model="confirmSave"
      type="confirm"
      :title="$t('authorNorm.saveTitle')"
      color="primary"
      :confirm-loading="saving"
      @confirm="doSave"
    >
      {{ $t('authorNorm.saveConfirm', { n: aliasRules.length }) }}
    </AppDialog>

    <AppDialog
      v-model="resultDialog"
      type="action"
      :title="$t('authorNorm.savedTitle')"
      color="success"
    >
      {{ resultMsg }}
    </AppDialog>
  </v-container>
</template>

<script>
export default {
  data() {
    return {
      tab: 0,
      scanning: false,
      scanned: false,
      report: null,
      saving: false,
      confirmSave: false,
      resultDialog: false,
      resultMsg: "",
      aliasRules: [],
      neverMerge: [],
      testName: "",
      testing: false,
      testResult: null,
    };
  },
  computed: {
    hasFindings() {
      const r = this.report;
      return r && (r.duplicates.length || r.suspects.length || r.dirty.length);
    },
  },
  mounted() {
    this.loadAlias();
  },
  methods: {
    doScan() {
      this.scanning = true;
      this.$backend("/admin/author_norm/scan")
        .then((rsp) => {
          if (rsp.err !== "ok") {
            this.$alert("error", rsp.msg);
            return;
          }
          this.report = rsp.report || {};
          this.scanned = true;
        })
        .catch(() => this.$alert("error", this.$t("authorNorm.scanFailed")))
        .finally(() => { this.scanning = false; });
    },
    loadAlias() {
      this.$backend("/admin/author_norm/alias")
        .then((rsp) => {
          if (rsp.err !== "ok") return;
          const data = rsp.data || {};
          const canonical = data.canonical || {};
          this.aliasRules = Object.keys(canonical).map((key) => ({
            key: key,
            name: canonical[key].name || "",
            aliases: (canonical[key].aliases || []).slice(),
            note: canonical[key].note || "",
            _newAlias: "",
          }));
          this.neverMerge = data.never_merge || [];
        })
        .catch(() => {});
    },
    addRule(canonicalName, aliases) {
      // 从体检页点过来：先把别名表 Tab 打开，再插一条新规则
      const exists = this.aliasRules.find((r) => r.name === canonicalName);
      const newAliases = (aliases || []).filter((a) => a && a !== canonicalName);
      if (exists) {
        newAliases.forEach((a) => {
          if (exists.aliases.indexOf(a) < 0) exists.aliases.push(a);
        });
      } else {
        this.aliasRules.push({
          key: canonicalName,
          name: canonicalName,
          aliases: newAliases,
          note: "",
          _newAlias: "",
        });
      }
      this.tab = 1;
      this.$alert("success", this.$t("authorNorm.ruleStaged", { name: canonicalName || "?" }));
    },
    commitAlias(rule) {
      const v = (rule._newAlias || "").trim();
      if (v && rule.aliases.indexOf(v) < 0) rule.aliases.push(v);
      rule._newAlias = "";
    },
    otherNames(group) {
      return (group.variants || []).map((v) => v.name).filter((n) => n !== group.canonical);
    },
    saveAlias() {
      this.aliasRules.forEach((r) => this.commitAlias(r));
      this.confirmSave = true;
    },
    doSave() {
      const canonical = {};
      this.aliasRules.forEach((r) => {
        const name = (r.name || "").trim();
        if (!name) return;
        canonical[name] = {
          name: name,
          aliases: (r.aliases || []).filter((a) => (a || "").trim()),
          note: r.note || "",
        };
      });
      this.saving = true;
      this.$backend("/admin/author_norm/alias", {
        method: "POST",
        body: JSON.stringify({ canonical: canonical, never_merge: this.neverMerge }),
      })
        .then((rsp) => {
          this.confirmSave = false;
          if (rsp.err !== "ok") {
            this.$alert("error", rsp.msg);
            return;
          }
          this.resultMsg = rsp.msg;
          this.resultDialog = true;
          const data = rsp.data || {};
          const c = data.canonical || {};
          this.aliasRules = Object.keys(c).map((key) => ({
            key: key,
            name: c[key].name || "",
            aliases: (c[key].aliases || []).slice(),
            note: c[key].note || "",
            _newAlias: "",
          }));
        })
        .catch(() => {
          this.confirmSave = false;
          this.$alert("error", this.$t("authorNorm.saveFailed"));
        })
        .finally(() => { this.saving = false; });
    },
    doTest() {
      if (!this.testName) return;
      this.testing = true;
      this.testResult = null;
      this.$backend("/admin/author_norm/test", {
        method: "POST",
        body: JSON.stringify({ name: this.testName }),
      })
        .then((rsp) => {
          if (rsp.err !== "ok") {
            this.$alert("error", rsp.msg);
            return;
          }
          this.testResult = rsp;
        })
        .catch(() => this.$alert("error", this.$t("authorNorm.testFailed")))
        .finally(() => { this.testing = false; });
    },
  },
};
</script>

<style scoped>
.norm-dup { border-left: 3px solid var(--v-success-base); }
.norm-sus { border-left: 3px solid var(--v-warning-base); }
.norm-dirty { border-left: 3px solid var(--v-orange-base, orange); }
.norm-table { background: transparent !important; }
.norm-table >>> th,
.norm-table >>> td { padding: 4px 8px !important; height: auto !important; }
</style>
