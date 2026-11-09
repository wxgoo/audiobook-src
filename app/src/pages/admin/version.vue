<template>
  <v-container fluid class="pa-4">
    <!-- 页头 -->
    <v-row class="mb-3" align="center">
      <v-col>
        <span class="text-h5 font-weight-bold">{{ $t('versionCheck.pageTitle') }}</span>
        <div class="text-caption grey--text mt-1">{{ $t('versionCheck.pageSubtitle') }}</div>
      </v-col>
      <v-col cols="auto">
        <v-btn small color="primary" :loading="checking" @click="checkNow">
          <v-icon small left>mdi-refresh</v-icon>{{ $t('versionCheck.checkNow') }}
        </v-btn>
      </v-col>
    </v-row>

    <!-- 当前版本 -->
    <v-card outlined class="mb-4">
      <v-card-title class="text-subtitle-1">
        <v-icon small left color="primary">mdi-tag-outline</v-icon>{{ $t('versionCheck.currentCard') }}
      </v-card-title>
      <v-card-text>
        <!-- 基线自检：包内发布清单读不到时，不显示"发现新版本"，直接报警 -->
        <v-alert v-if="st.baseline_ok === false" type="error" dense text class="mb-3">
          <div class="text-body-2 font-weight-medium">{{ $t('versionCheck.baselineMissingTitle') }}</div>
          <div class="text-caption mt-1">{{ $t('versionCheck.baselineMissingHint') }}</div>
          <div class="text-caption mt-1" style="word-break:break-all">CODE_ROOT: {{ st.baseline_code_root || '—' }}</div>
          <div class="text-caption" style="word-break:break-all">{{ st.baseline_path || '—' }}</div>
        </v-alert>
        <v-row dense>
          <v-col cols="12" sm="4">
            <div class="text-caption grey--text">{{ $t('versionCheck.currentVersion') }}</div>
            <div class="text-body-1 font-weight-medium">{{ st.version || '—' }}</div>
          </v-col>
          <v-col cols="12" sm="4">
            <div class="text-caption grey--text">{{ $t('versionCheck.currentRevision') }}</div>
            <div class="text-body-1 font-weight-medium">{{ st.current && st.current.revision || '—' }}</div>
            <div class="text-caption grey--text">{{ st.current && st.current.summary }}</div>
          </v-col>
          <v-col cols="12" sm="4">
            <div class="text-caption grey--text">{{ $t('versionCheck.checkedAt') }}</div>
            <div class="text-body-2">{{ st.checked_at || '—' }}</div>
          </v-col>
        </v-row>
        <v-divider class="my-3" />
        <v-switch
          v-model="autoCheck"
          :label="$t('versionCheck.autoCheck')"
          :hint="$t('versionCheck.autoCheckHint')"
          persistent-hint
          dense
          hide-details="auto"
          @change="toggleAuto"
        />
      </v-card-text>
    </v-card>

    <v-alert v-if="st.check_error" type="warning" dense outlined class="mb-4">
      <div class="text-body-2 font-weight-medium">{{ $t('versionCheck.checkFailed') }}</div>
      <div class="text-caption mt-1">{{ st.check_error }}</div>
      <div class="text-caption mt-1">{{ $t('versionCheck.checkFailedHint') }}</div>
    </v-alert>

    <v-alert v-if="st.need_persist" type="warning" dense outlined class="mb-4">
      <div class="text-body-2 font-weight-medium">{{ $t('versionCheck.persistTitle') }}</div>
      <div class="text-caption mt-1">{{ $t('versionCheck.persistHint', { rev: st.persist_revision }) }}</div>
    </v-alert>

    <!-- 更新中 / 重启中 -->
    <v-alert v-if="busy || restarting" type="info" dense colored-border border="left" class="mb-4">
      <div class="text-body-2 font-weight-medium">
        {{ busy ? $t('versionCheck.applying') : $t('versionCheck.restartTitle') }}
      </div>
      <div class="text-caption mt-1">{{ busy ? $t('versionCheck.applyingHint') : $t('versionCheck.restartHint') }}</div>
      <v-progress-linear indeterminate class="mt-2" />
    </v-alert>
    <v-alert v-else-if="restartFailed" type="error" dense outlined class="mb-4">
      <div class="text-body-2 font-weight-medium">{{ $t('versionCheck.restartFailed') }}</div>
      <div class="text-caption mt-1" v-text="rollbackCommand"></div>
    </v-alert>

    <!-- 已是最新 -->
    <v-alert v-if="!st.has_update && !st.check_error && !busy" type="success" dense outlined class="mb-4">
      <div class="text-body-2 font-weight-medium">{{ $t('versionCheck.upToDate') }}</div>
      <div class="text-caption mt-1">{{ $t('versionCheck.upToDateHint') }}</div>
    </v-alert>

    <!-- 有新版本 -->
    <v-card v-if="st.has_update && st.latest" outlined class="mb-4">
      <v-card-title class="text-subtitle-1">
        <v-icon small left :color="st.mode === 'hotfix' ? 'success' : 'orange'">
          {{ st.mode === 'hotfix' ? 'mdi-download-circle-outline' : 'mdi-package-up' }}
        </v-icon>
        {{ $t('versionCheck.newVersionTitle', { rev: st.latest.revision }) }}
      </v-card-title>
      <v-card-text>
        <div class="text-body-2 mb-2">{{ st.latest.summary }}</div>
        <div class="text-caption grey--text mb-3">
          {{ $t('versionCheck.date') }}: {{ st.latest.date || '—' }} ·
          {{ $t('versionCheck.revision') }}: {{ st.latest.base_revision || '—' }} → {{ st.latest.revision }}
        </div>

        <ul v-if="st.latest.notes && st.latest.notes.length" class="text-body-2 mb-3 ml-4">
          <li v-for="(n, i) in st.latest.notes" :key="i">{{ n }}</li>
        </ul>

        <!-- 可在线更新 -->
        <template v-if="st.can_apply">
          <v-alert type="success" dense text class="mb-3">
            <div class="text-body-2 font-weight-medium">{{ $t('versionCheck.hotfixTitle') }}</div>
            <div class="text-caption mt-1">{{ $t('versionCheck.hotfixHint') }}</div>
          </v-alert>
          <div class="text-caption mb-1">
            {{ $t('versionCheck.hotfixFiles', { n: st.latest.files.length }) }}
          </div>
          <div class="text-caption grey--text mb-3" style="word-break: break-all">
            {{ st.latest.files.map(f => f.path).join('，') }}
          </div>
          <v-btn color="success" :loading="busy" :disabled="busy || restarting" @click="confirmApply = true">
            <v-icon small left>mdi-download</v-icon>{{ $t('versionCheck.applyNow') }}
          </v-btn>
        </template>

        <!-- 需要重新部署 -->
        <template v-else-if="st.mode === 'redeploy'">
          <v-alert type="warning" dense text class="mb-3">
            <div class="text-body-2 font-weight-medium">{{ $t('versionCheck.redeployTitle') }}</div>
            <div class="text-caption mt-1">{{ st.latest.reason }}</div>
          </v-alert>
          <div class="text-caption mb-3">{{ $t('versionCheck.redeployHint') }}</div>
          <div v-if="st.latest.changed && st.latest.changed.blocking.length" class="text-caption mb-2">
            <b>{{ $t('versionCheck.changedBlocking') }}：</b>
            <span style="word-break: break-all">{{ st.latest.changed.blocking.join('，') }}</span>
          </div>
          <div class="text-caption font-weight-medium mb-1">{{ $t('versionCheck.redeployCommands') }}</div>
          <!-- 点击整块全选，配合 Ctrl+C；内网站点常是 HTTP，剪贴板 API 不可用 -->
          <pre ref="cmdPre" class="version-pre" @click="selectCommands">{{ (st.latest.deploy_commands || []).join('\n') }}</pre>
          <v-btn small text color="primary" class="mt-2 px-0" @click="copyCommands">
            <v-icon small left>mdi-content-copy</v-icon>{{ $t('versionCheck.copyCommands') }}
          </v-btn>
        </template>

        <template v-else>
          <v-alert type="info" dense text class="mb-1">
            <div class="text-body-2 font-weight-medium">{{ $t('versionCheck.docsOnlyTitle') }}</div>
            <div class="text-caption mt-1">{{ $t('versionCheck.docsOnlyHint') }}</div>
          </v-alert>
        </template>
      </v-card-text>
    </v-card>

    <!-- 备份与回滚 -->
    <v-card outlined class="mb-4">
      <v-card-title class="text-subtitle-1">
        <v-icon small left>mdi-backup-restore</v-icon>{{ $t('versionCheck.rollbackTitle') }}
      </v-card-title>
      <v-card-text>
        <div class="text-caption grey--text mb-2">{{ $t('versionCheck.rollbackHint') }}</div>
        <div v-if="!st.backups || !st.backups.length" class="text-caption grey--text">
          {{ $t('versionCheck.noBackups') }}
        </div>
        <v-list v-else dense>
          <v-list-item v-for="b in st.backups" :key="b.id">
            <v-list-item-content>
              <v-list-item-title class="text-body-2">
                {{ $t('versionCheck.backupItem', { from: b.from || '—', to: b.to || '—', n: b.files }) }}
              </v-list-item-title>
              <v-list-item-subtitle class="text-caption">{{ b.date }} · {{ b.id }}</v-list-item-subtitle>
            </v-list-item-content>
            <v-list-item-action>
              <v-btn small text color="error" :disabled="busy || restarting" @click="askRollback(b.id)">
                {{ $t('versionCheck.rollbackNow') }}
              </v-btn>
            </v-list-item-action>
          </v-list-item>
        </v-list>
      </v-card-text>
    </v-card>

    <!-- 仓库最近提交 -->
    <v-card v-if="st.commits && st.commits.length" outlined class="mb-4">
      <v-card-title class="text-subtitle-1">
        <v-icon small left>mdi-source-branch</v-icon>{{ $t('versionCheck.recentCommits') }}
      </v-card-title>
      <v-card-text class="pt-0">
        <div v-for="c in st.commits" :key="c.sha" class="text-caption mb-1">
          <span class="grey--text">{{ c.date }}</span>
          <code class="mx-2">{{ c.sha }}</code>
          {{ c.message }}
        </div>
      </v-card-text>
    </v-card>

    <!-- 确认对话框 -->
    <v-dialog v-model="confirmApply" max-width="520">
      <v-card>
        <v-card-title class="text-subtitle-1">{{ $t('versionCheck.applyConfirmTitle') }}</v-card-title>
        <v-card-text class="text-body-2">{{ $t('versionCheck.applyConfirmText') }}</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn small text @click="confirmApply = false">{{ $t('versionCheck.cancel') }}</v-btn>
          <v-btn small color="success" @click="applyUpdate">{{ $t('versionCheck.applyNow') }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="confirmRollback" max-width="520">
      <v-card>
        <v-card-title class="text-subtitle-1">{{ $t('versionCheck.rollbackConfirmTitle') }}</v-card-title>
        <v-card-text class="text-body-2">{{ $t('versionCheck.rollbackConfirmText') }}</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn small text @click="confirmRollback = false">{{ $t('versionCheck.cancel') }}</v-btn>
          <v-btn small color="error" @click="doRollback">{{ $t('versionCheck.rollbackNow') }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script>
// 「版本与更新」独立页：检测源是 Gitee 仓库的 update/manifest.json，
// 与「系统设置 → 工具箱」里那几个功能开关完全解耦。
export default {
  data() {
    return {
      st: { version: '', current: {}, latest: null, has_update: false,
            mode: 'none', can_apply: false, check_error: '', checked_at: '',
            commits: [], backups: [], need_persist: false, persist_revision: '',
            auto_check: true },
      autoCheck: true,
      checking: false,
      busy: false,
      restarting: false,
      restartFailed: false,
      confirmApply: false,
      confirmRollback: false,
      rollbackId: '',
    };
  },
  computed: {
    rollbackCommand() {
      return 'docker cp /volume1/docker/audiobook-data/update-backup/<备份目录>/webserver/. '
           + 'audiobook-mybooks-1:/var/www/mybooks/webserver/ && docker restart audiobook-mybooks-1';
    },
  },
  mounted() {
    this.$store.commit('navbar', true);
    this.load(false);
  },
  methods: {
    async load(force) {
      this.checking = force;
      try {
        const rsp = await this.$backend('/admin/version/status' + (force ? '?force=1' : ''));
        if (rsp && rsp.err === 'ok') {
          this.st = rsp;
          this.autoCheck = rsp.auto_check !== false;
        }
      } catch (e) {
        this.st.check_error = String(e);
      } finally {
        this.checking = false;
      }
    },
    async checkNow() {
      try {
        this.checking = true;
        const rsp = await this.$backend('/admin/version/check', { method: 'POST' });
        if (rsp && rsp.err === 'ok') {
          this.st = rsp;
          this.autoCheck = rsp.auto_check !== false;
          this.$alert('success', rsp.msg);
        } else {
          this.$alert('error', (rsp && (rsp.msg || rsp.err)) || 'check failed');
        }
      } catch (e) {
        this.$alert('error', String(e));
      } finally {
        this.checking = false;
      }
    },
    async toggleAuto(val) {
      try {
        const rsp = await this.$backend('/admin/version/auto?enabled=' + (val ? '1' : '0'),
                                        { method: 'POST' });
        if (rsp && rsp.err === 'ok') {
          this.$alert('success', rsp.msg);
        } else {
          this.autoCheck = !val;
          this.$alert('error', (rsp && (rsp.msg || rsp.err)) || 'save failed');
        }
      } catch (e) {
        this.autoCheck = !val;
        this.$alert('error', String(e));
      }
    },
    async applyUpdate() {
      this.confirmApply = false;
      this.busy = true;
      this.restartFailed = false;
      try {
        const rev = this.st.latest && this.st.latest.revision;
        const rsp = await this.$backend('/admin/version/apply?revision=' + encodeURIComponent(rev),
                                        { method: 'POST' });
        if (!rsp || rsp.err !== 'ok') {
          this.$alert('error', (rsp && (rsp.msg || rsp.err)) || 'apply failed');
          this.busy = false;
          return;
        }
        this.busy = false;
        this.restarting = true;
        this.waitRecover();
      } catch (e) {
        this.$alert('error', String(e));
        this.busy = false;
      }
    },
    askRollback(id) {
      this.rollbackId = id || '';
      this.confirmRollback = true;
    },
    async doRollback() {
      this.confirmRollback = false;
      this.busy = true;
      try {
        const rsp = await this.$backend('/admin/version/rollback?backup_id=' +
                                        encodeURIComponent(this.rollbackId), { method: 'POST' });
        if (!rsp || rsp.err !== 'ok') {
          this.$alert('error', (rsp && (rsp.msg || rsp.err)) || 'rollback failed');
          this.busy = false;
          return;
        }
        this.busy = false;
        this.restarting = true;
        this.waitRecover();
      } catch (e) {
        this.$alert('error', String(e));
        this.busy = false;
      }
    },
    // 进程退出后 supervisor 拉起，期间请求会失败；用原生 fetch 轮询，避免
    // $backend 把 302/非 200 当成「服务启动中」重定向到 /starting。
    async waitRecover() {
      for (let i = 0; i < 30; i++) {
        await new Promise(r => setTimeout(r, 3000));
        try {
          const rsp = await fetch('/api/admin/version/status', { credentials: 'include' });
          if (rsp.ok) {
            const data = await rsp.json();
            if (data && data.err === 'ok') {
              window.location.reload();
              return;
            }
          }
        } catch (e) { /* 还在重启，继续等 */ }
      }
      this.restarting = false;
      this.restartFailed = true;
    },
    selectCommands() {
      // 点一下整块全选：即使 execCommand 也失败，用户直接 Ctrl+C 就能复制
      const el = this.$refs.cmdPre;
      if (!el || !window.getSelection || !document.createRange) return;
      const range = document.createRange();
      range.selectNodeContents(el);
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
    },
    async copyCommands() {
      const text = ((this.st.latest && this.st.latest.deploy_commands) || []).join('\n');
      if (!text) {
        this.$alert('error', this.$t('versionCheck.copyFailed'));
        return;
      }
      // 1) 现代剪贴板 API：仅 HTTPS / localhost 等安全上下文可用
      if (navigator.clipboard && window.isSecureContext) {
        try {
          await navigator.clipboard.writeText(text);
          this.$alert('success', this.$t('versionCheck.copied'));
          return;
        } catch (e) { /* 落到降级 */ }
      }
      // 2) execCommand 降级：textarea 必须留在视口内，否则部分浏览器拒绝复制视口外元素
      try {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.setAttribute('readonly', '');
        ta.style.position = 'fixed';
        ta.style.top = '0';
        ta.style.left = '0';
        ta.style.width = '1px';
        ta.style.height = '1px';
        ta.style.opacity = '0';
        ta.style.pointerEvents = 'none';
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        ta.setSelectionRange(0, ta.value.length);
        const ok = document.execCommand('copy');
        document.body.removeChild(ta);
        if (ok) {
          this.$alert('success', this.$t('versionCheck.copied'));
          return;
        }
      } catch (e) { /* 落到手动全选 */ }
      // 3) 最终兜底：自动选中命令块并给中性提示（不弹错误框抢焦点，保证 Ctrl+C 可用）
      this.selectCommands();
      this.$alert('info', this.$t('versionCheck.copyManual'));
    },
  },
};
</script>

<style scoped>
.version-pre {
  background: rgba(127, 127, 127, 0.12);
  border-radius: 4px;
  padding: 10px 12px;
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-all;
  overflow-x: auto;
}
</style>
