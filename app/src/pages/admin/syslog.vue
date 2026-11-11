<template>
  <v-container fluid class="pa-3">
    <v-row align="center" class="mb-2">
      <v-col>
        <span class="text-h6">{{ $t('syslog.title') }}</span>
        <span class="ml-2 text-caption grey--text">{{ $t('syslog.subtitle') }}</span>
      </v-col>
      <v-col cols="auto">
        <v-btn small color="primary" class="mr-2" :loading="loading" @click="fetchLog">
          <v-icon small left>mdi-refresh</v-icon>{{ $t('syslog.refresh') }}
        </v-btn>
        <v-btn small color="primary" :href="this.logLink" target="_blank" :disabled="this.logLink == null">
          <v-icon small left>mdi-download</v-icon>{{ $t('syslog.download') }}
        </v-btn>
      </v-col>
    </v-row>

    <v-alert v-if="error" type="error" dense class="mb-2">{{ error }}</v-alert>

    <v-sheet outlined rounded class="log-container pa-3" :style="containerStyle">
      <pre class="log-content" :style="contentStyle" ref="logBox">{{ logText }}</pre>
    </v-sheet>

    <v-row align="center" class="mb-2">
      <v-col>
      </v-col>
      <v-col cols="auto">
        <v-btn small color="primary" class="mr-2" :loading="loading" @click="fetchLog">
          <v-icon small left>mdi-refresh</v-icon>{{ $t('syslog.refresh') }}
        </v-btn>
        <v-btn small color="primary" :href="this.logLink" target="_blank" :disabled="this.logLink == null">
          <v-icon small left>mdi-download</v-icon>{{ $t('syslog.download') }}
        </v-btn>
      </v-col>
    </v-row>
  </v-container>
</template>

<script>
export default {
  data: () => ({
    lines: [],
    loading: false,
    error: null,
    logLink: null,
    ssr_loaded: false,
  }),
  computed: {
    logText() {
      return this.lines.length ? this.lines.join("\n") : this.$t('syslog.empty');
    },
    isDark() {
      return this.$vuetify.theme.dark;
    },
    containerStyle() {
      return {
        background: this.isDark ? '#1e1e1e' : '#f5f5f5',
      };
    },
    contentStyle() {
      return {
        color: this.isDark ? '#d4d4d4' : '#1e1e1e',
      };
    },
  },
  head() {
    return { title: this.$t('syslog.pageTitle') };
  },
  async asyncData({ app, res }) {
    if (res !== undefined) {
      res.setHeader("Cache-Control", "no-cache");
    }
    try {
      const data = await app.$backend("/admin/syslog");
      const payload = { lines: data.lines || [], error: data.err !== "ok" ? data.msg : null, logLink: data.href || null };
      // 静态产物里 asyncData 只在构建期执行，构建期的结果不能当成运行时已加载
      if (data.err === "ok") {
        payload.ssr_loaded = true;
      }
      return payload;
    } catch (e) {
      return { lines: [], error: String(e) };
    }
  },
  created() {
    this.$store.commit("navbar", true);
  },
  mounted() {
    // 直接进入/强刷时补一次取数；服务端已取到数据则不重复请求
    if (!this.ssr_loaded) {
      this.fetchLog();
    }
  },
  methods: {
    async fetchLog() {
      this.loading = true;
      this.error = null;
      try {
        const data = await this.$backend("/admin/syslog");
        if (data.err === "ok") {
          this.lines = data.lines || [];
        } else {
          this.error = data.msg || this.$t('syslog.fetchFailed');
        }
      } catch (e) {
        this.error = String(e);
      } finally {
        this.loading = false;
        this.$nextTick(() => {
          const box = this.$refs.logBox;
          if (box) box.parentElement.scrollTop = box.parentElement.scrollHeight;
        });
      }
    },
  },
};
</script>

<style scoped>
.log-container {
  max-height: 78vh;
  overflow-y: auto;
}
.log-content {
  font-family: "Consolas", "Menlo", "Monaco", "Courier New", monospace;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}
</style>
