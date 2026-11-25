<template>
  <v-container fluid class="pa-4">
    <!-- 页头 -->
    <v-row class="mb-3" align="center">
      <v-col class="text-center">
        <span class="text-h5 font-weight-bold">{{ $t('ebookTagsCleaner.title') }}</span>
      </v-col>
      <v-col cols="auto">
        <v-btn small color="error" @click="$router.go(-1)">
          <v-icon small left>mdi-close</v-icon>{{ $t('ebookTagsCleaner.close') }}
        </v-btn>
      </v-col>
    </v-row>

    <v-row justify="center">
      <v-col cols="12" md="10" lg="9">
        <!-- 说明 -->
        <v-alert type="info" text dense class="mb-4">
          <div class="text-body-2">{{ $t('ebookTagsCleaner.subtitle') }}</div>
        </v-alert>

        <!-- 清理规则 -->
        <v-card rounded="xl" outlined class="pa-5 mb-4">
          <div class="text-subtitle-1 font-weight-medium mb-3">
            {{ $t('ebookTagsCleaner.rulesTitle') }}
          </div>

          <div v-if="rulesLoading" class="text-body-2 text--secondary">
            {{ $t('ebookTagsCleaner.rulesLoading') }}
          </div>
          <v-alert v-else-if="rulesError" type="error" dense text>
            {{ rulesError }}
          </v-alert>

          <v-card
            v-for="rule in rules"
            :key="rule.id"
            rounded="lg"
            outlined
            class="pa-3 mb-2"
          >
            <div class="text-body-1 font-weight-medium mb-1">{{ rule.title }}</div>
            <div class="text-body-2 text--secondary">{{ rule.description }}</div>
            <div v-if="rule.examples && rule.examples.length" class="mt-2 d-flex flex-wrap" style="gap: 6px">
              <v-chip v-for="(ex, i) in rule.examples" :key="i" small label outlined>
                {{ ex }}
              </v-chip>
            </div>
          </v-card>
        </v-card>

        <!-- 开始清理 -->
        <v-card rounded="xl" outlined class="pa-5">
          <div class="text-subtitle-1 font-weight-medium mb-3">
            {{ $t('ebookTagsCleaner.taskTitle') }}
          </div>

          <div class="d-flex align-center flex-wrap" style="gap: 10px">
            <span class="text-body-2">{{ $t('ebookTagsCleaner.rareTagCount') }}</span>
            <v-text-field
              v-model="rareTagCount"
              type="number"
              :min="0"
              :max="maxRareTagCount"
              step="1"
              outlined
              dense
              hide-details
              :disabled="running"
              style="max-width: 110px"
              class="shrink"
            ></v-text-field>
          </div>
          <div class="text-caption text--secondary mt-2">{{ rareTagHint }}</div>

          <v-alert v-if="startError" type="error" dense text class="mt-3 mb-0">
            {{ startError }}
          </v-alert>

          <div class="d-flex align-center flex-wrap mt-3" style="gap: 12px">
            <v-btn
              color="primary"
              :disabled="running || confirmPending"
              @click="onStartClick"
            >
              <v-icon small left>mdi-tag-remove</v-icon>
              {{ $t('ebookTagsCleaner.start') }}
            </v-btn>
            <v-btn
              v-if="running"
              color="secondary"
              :disabled="cancelling"
              @click="doCancel"
            >
              {{ cancelling ? $t('ebookTagsCleaner.cancelling') : $t('ebookTagsCleaner.cancel') }}
            </v-btn>
            <v-progress-circular
              v-if="running"
              indeterminate
              size="22"
              width="2"
            ></v-progress-circular>
          </div>

          <!-- 任务面板 -->
          <div v-if="job && job.status !== 'idle'" class="mt-4">
            <div class="d-flex justify-space-between text-caption text--secondary mb-1">
              <span>{{ phaseText }}</span>
              <span>{{ phaseProcessed }} / {{ phaseTotal }}</span>
            </div>
            <v-progress-linear :value="progressPct" rounded height="8"></v-progress-linear>

            <div class="d-flex flex-wrap mt-4" style="gap: 24px">
              <div style="min-width: 88px">
                <div class="text-h6 font-weight-bold">{{ job.total || 0 }}</div>
                <div class="text-caption text--secondary">{{ $t('ebookTagsCleaner.statTotal') }}</div>
              </div>
              <div style="min-width: 88px">
                <div class="text-h6 font-weight-bold success--text">{{ job.changed || 0 }}</div>
                <div class="text-caption text--secondary">{{ $t('ebookTagsCleaner.statChanged') }}</div>
              </div>
              <div style="min-width: 88px">
                <div class="text-h6 font-weight-bold">{{ job.unchanged || 0 }}</div>
                <div class="text-caption text--secondary">{{ $t('ebookTagsCleaner.statUnchanged') }}</div>
              </div>
              <div style="min-width: 88px">
                <div class="text-h6 font-weight-bold error--text">{{ job.errors || 0 }}</div>
                <div class="text-caption text--secondary">{{ $t('ebookTagsCleaner.statErrors') }}</div>
              </div>
            </div>

            <div v-if="running && job.current_book" class="text-caption text--secondary mt-2">
              {{ $t('ebookTagsCleaner.currentBook', { title: job.current_book }) }}
            </div>

            <v-alert
              v-if="job.status === 'failed' && job.error"
              type="error"
              dense
              text
              class="mt-3 mb-0"
            >
              {{ $t('ebookTagsCleaner.taskError', { error: job.error }) }}
            </v-alert>

            <div v-if="job.error_samples && job.error_samples.length" class="mt-3">
              <div class="text-caption text--secondary">
                {{ $t('ebookTagsCleaner.errorSamples') }}
              </div>
              <div
                v-for="(sample, i) in job.error_samples"
                :key="i"
                class="text-caption text--secondary"
              >
                book_id={{ sample.book_id }}：{{ sample.error }}
              </div>
            </div>
          </div>
        </v-card>
      </v-col>
    </v-row>

    <!-- 启动确认 -->
    <v-dialog v-model="confirmDialog" max-width="420">
      <v-card rounded="xl">
        <v-card-title class="text-h6">{{ $t('ebookTagsCleaner.confirmTitle') }}</v-card-title>
        <v-card-text class="text-body-2">
          {{ $t('ebookTagsCleaner.confirmMessage') }}
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn text @click="confirmDialog = false">{{ $t('ebookTagsCleaner.cancel') }}</v-btn>
          <v-btn color="error" text @click="doStart">{{ $t('ebookTagsCleaner.start') }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script>
export default {
  data() {
    return {
      rules: [],
      rulesLoading: true,
      rulesError: "",
      maxRareTagCount: 3,
      rareTagCount: 0,
      bookCount: null,
      job: null,
      pollTimer: null,
      confirmDialog: false,
      confirmPending: false,
      startError: "",
      cancelling: false,
    };
  },
  computed: {
    running() {
      return !!this.job && this.job.status === "running";
    },
    phaseText() {
      const job = this.job || {};
      if (this.running) {
        return this.$t(
          job.phase === "scanning"
            ? "ebookTagsCleaner.phaseScanning"
            : "ebookTagsCleaner.phaseCleaning"
        );
      }
      return this.$t(`ebookTagsCleaner.status_${job.status || "idle"}`);
    },
    phaseTotal() {
      const job = this.job || {};
      const scanning = this.running && job.phase === "scanning";
      if (scanning) return job.scan_total || 0;
      // target_total 为 0 是合法值（没有需要处理的书籍），不能退回 total
      return typeof job.target_total === "number" ? job.target_total : job.total || 0;
    },
    phaseProcessed() {
      const job = this.job || {};
      const scanning = this.running && job.phase === "scanning";
      return scanning ? job.scanned || 0 : job.processed || 0;
    },
    progressPct() {
      const job = this.job || {};
      const phaseTotal = this.phaseTotal;
      if (this.running && job.phase === "scanning") {
        return phaseTotal ? Math.round((this.phaseProcessed / phaseTotal) * 50) : 0;
      }
      if (job.status === "completed") return 100;
      const base = job.rare_tag_count ? 50 : 0;
      return phaseTotal
        ? base + Math.round((this.phaseProcessed / phaseTotal) * (100 - base))
        : 100;
    },
    rareTagHint() {
      if (typeof this.bookCount === "number") {
        return this.$t("ebookTagsCleaner.rareTagHint", {
          max: this.maxRareTagCount,
          bookCount: this.bookCount,
        });
      }
      return this.$t("ebookTagsCleaner.rareTagHintNoCount", { max: this.maxRareTagCount });
    },
  },
  mounted() {
    this.loadLimits();
    this.loadRules();
    this.refreshStatus();
  },
  beforeDestroy() {
    this.stopPolling();
  },
  methods: {
    api(path) {
      return `/toolbox/ebook_tags_cleaner/${path}`;
    },
    loadRules() {
      this.rulesLoading = true;
      this.rulesError = "";
      this.$backend(this.api("rules"))
        .then((rsp) => {
          if (rsp.err !== "ok") throw new Error(rsp.msg || rsp.err);
          this.rules = rsp.data || [];
        })
        .catch((err) => {
          this.rulesError = this.$t("ebookTagsCleaner.rulesLoadFailed", {
            error: err.message || err,
          });
        })
        .finally(() => {
          this.rulesLoading = false;
        });
    },
    loadLimits() {
      this.$backend(this.api("limits"))
        .then((rsp) => {
          if (rsp.err !== "ok") throw new Error(rsp.msg || rsp.err);
          const limits = rsp.data || {};
          this.bookCount = Number(limits.book_count);
          let max = Number(limits.max_rare_tag_count);
          if (!Number.isInteger(max) || max < 1 || max > 3) max = 3;
          this.maxRareTagCount = max;
          const cur = Number(this.rareTagCount) || 0;
          this.rareTagCount = Math.min(cur, max);
        })
        .catch(() => {
          this.maxRareTagCount = 3;
        });
    },
    startPolling() {
      if (this.pollTimer) return;
      this.pollTimer = setInterval(this.refreshStatus, 1000);
    },
    stopPolling() {
      if (this.pollTimer) {
        clearInterval(this.pollTimer);
        this.pollTimer = null;
      }
    },
    refreshStatus() {
      return this.$backend(this.api("status"))
        .then((rsp) => {
          if (rsp.err !== "ok") throw new Error(rsp.msg || rsp.err);
          this.renderStatus(rsp.data);
        })
        .catch(() => {
          /* 静默失败，下一轮再试 */
        });
    },
    renderStatus(job) {
      this.job = job || { status: "idle" };
      if (this.running) {
        this.startPolling();
      } else {
        this.stopPolling();
      }
    },
    onStartClick() {
      if (this.confirmPending) return;
      this.confirmPending = true;
      this.confirmDialog = true;
    },
    doStart() {
      this.confirmDialog = false;
      this.confirmPending = false;
      this.startError = "";
      let max = Number(this.maxRareTagCount);
      if (!Number.isInteger(max) || max < 1 || max > 3) max = 3;
      const rareTagCount = Math.min(Math.max(0, Math.floor(Number(this.rareTagCount) || 0)), max);
      this.rareTagCount = String(rareTagCount);
      this.$backend(this.api("start"), {
        method: "POST",
        body: JSON.stringify({ rare_tag_count: rareTagCount }),
      })
        .then((rsp) => {
          if (rsp.err !== "ok") throw new Error(rsp.msg || rsp.err);
          this.renderStatus(rsp.data);
        })
        .catch((err) => {
          this.startError = this.$t("ebookTagsCleaner.startFailed", {
            error: err.message || err,
          });
        });
    },
    doCancel() {
      this.cancelling = true;
      this.$backend(this.api("cancel"), { method: "POST" })
        .then((rsp) => {
          if (rsp.err !== "ok") throw new Error(rsp.msg || rsp.err);
          this.renderStatus(rsp.data);
        })
        .catch((err) => {
          this.$alert("error", this.$t("ebookTagsCleaner.taskError", {
            error: err.message || err,
          }));
        })
        .finally(() => {
          this.cancelling = false;
        });
    },
  },
};
</script>
