<template>
  <v-container fluid class="pa-4">
    <!-- 页头 -->
    <v-row class="mb-3" align="center">
      <v-col class="text-center">
        <span class="text-h5 font-weight-bold">{{ $t('dedup.title') }}</span>
      </v-col>
      <v-col cols="auto">
        <v-btn small color="error" @click="$router.go(-1)">
          <v-icon small left>mdi-close</v-icon>{{ $t('dedup.close') }}
        </v-btn>
      </v-col>
    </v-row>

    <v-row justify="center">
      <v-col cols="12" md="10" lg="9">
        <!-- 说明 -->
        <v-alert type="info" text dense class="mb-4">
          <div class="text-body-2">{{ $t('dedup.intro') }}</div>
          <div class="text-caption mt-1">{{ $t('dedup.intro2') }}</div>
        </v-alert>

        <!-- 操作区 -->
        <v-card rounded="xl" outlined class="pa-5">
          <div class="d-flex align-center flex-wrap" style="gap: 12px">
            <v-btn color="primary" :loading="scanning" @click="doScan">
              <v-icon small left>mdi-magnify-scan</v-icon>
              {{ scanning ? $t('dedup.scanning') : $t('dedup.scanBtn') }}
            </v-btn>

            <v-btn
              color="success"
              :disabled="!selectedMerge.length || applying"
              :loading="applying"
              @click="confirmApply"
            >
              <v-icon small left>mdi-merge</v-icon>
              {{ $t('dedup.applyBtn', { n: selectedMerge.length }) }}
            </v-btn>

            <v-checkbox
              v-model="doBackup"
              :label="$t('dedup.backupFirst')"
              hide-details
              class="mt-0 shrink"
            ></v-checkbox>
          </div>

          <div v-if="scanned" class="mt-3 text-caption text--secondary">
            {{ $t('dedup.summary', {
              total: summary.total_groups,
              mergeable: summary.mergeable,
              skipped: summary.skipped,
              del: summary.will_delete,
              move: summary.will_move_audio,
            }) }}
          </div>
        </v-card>

        <!-- 空结果 -->
        <v-card v-if="scanned && !groups.length" rounded="xl" outlined class="pa-8 mt-4 text-center">
          <v-icon size="56" color="success">mdi-check-decagram</v-icon>
          <div class="text-h6 mt-3">{{ $t('dedup.noDuplicates') }}</div>
          <div class="text-caption text--secondary mt-1">{{ $t('dedup.noDuplicatesHint') }}</div>
        </v-card>

        <!-- 结果列表 -->
        <div v-if="groups.length" class="mt-4">
          <v-card
            v-for="g in groups"
            :key="g.key"
            rounded="xl"
            outlined
            class="pa-4 mb-3"
            :class="g.action === 'merge' ? 'dedup-mergeable' : 'dedup-skip'"
          >
            <div class="d-flex align-start">
              <v-checkbox
                v-if="g.action === 'merge'"
                v-model="g._selected"
                hide-details
                class="mt-0 mr-2 shrink"
                @change="recount"
              ></v-checkbox>
              <v-icon
                :color="g.action === 'merge' ? 'success' : 'warning'"
                class="mr-2 mt-1"
              >
                {{ g.action === 'merge' ? 'mdi-merge' : 'mdi-alert-outline' }}
              </v-icon>

              <div class="flex-grow-1" style="min-width: 0">
                <div class="text-subtitle-1 font-weight-bold text-truncate">
                  {{ g.title || $t('dedup.untitled') }}
                </div>

                <!-- 可合并：展示保留/删除关系 -->
                <div v-if="g.action === 'merge'" class="mt-2">
                  <div class="text-caption text--secondary mb-1">
                    {{ $t('dedup.keepLabel') }}
                    <strong class="success--text">#{{ g.keep_book_id }}</strong>
                    <span v-if="g.reasons" class="ml-2 text-grey">（{{ g.reasons }}）</span>
                  </div>
                  <div class="text-caption text--secondary">
                    {{ $t('dedup.dropLabel') }}
                    <strong class="error--text">{{ g.drop_book_ids.map(i => '#' + i).join('、') }}</strong>
                  </div>

                  <!-- 每本书的明细 -->
                  <v-simple-table dense class="mt-2 dedup-table">
                    <thead>
                      <tr>
                        <th class="text-caption">ID</th>
                        <th class="text-caption">{{ $t('dedup.colEbook') }}</th>
                        <th class="text-caption">{{ $t('dedup.colAudio') }}</th>
                        <th class="text-caption">{{ $t('dedup.colAction') }}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="b in g.books" :key="b.book_id">
                        <td class="text-caption">#{{ b.book_id }}</td>
                        <td class="text-caption">
                          {{ b.ebook_formats.length ? b.ebook_formats.join('/') : '—' }}
                        </td>
                        <td class="text-caption">
                          {{ b.audio_count ? $t('dedup.audioCount', { n: b.audio_count }) : '—' }}
                        </td>
                        <td class="text-caption">
                          <v-chip
                            x-small
                            :color="b.book_id === g.keep_book_id ? 'success' : 'error'"
                            dark
                          >
                            {{ b.book_id === g.keep_book_id ? $t('dedup.keep') : $t('dedup.drop') }}
                          </v-chip>
                        </td>
                      </tr>
                    </tbody>
                  </v-simple-table>
                </div>

                <!-- 跳过：说明原因 -->
                <div v-else class="mt-1 text-caption warning--text">
                  {{ g.reason }}
                </div>
              </div>
            </div>
          </v-card>
        </div>

        <!-- 结果 -->
        <v-card v-if="resultMsg" rounded="xl" outlined class="pa-4 mt-4">
          <div class="d-flex align-center">
            <v-icon :color="resultFailed ? 'warning' : 'success'" class="mr-2">
              {{ resultFailed ? 'mdi-alert-circle-outline' : 'mdi-check-circle' }}
            </v-icon>
            <span class="text-body-2">{{ resultMsg }}</span>
          </div>
          <div v-if="backupPath" class="text-caption text--secondary mt-2">
            {{ $t('dedup.backupPath') }}<code>{{ backupPath }}</code>
          </div>
          <div v-if="resultFailed" class="text-caption text--secondary mt-1">
            {{ $t('dedup.failedHint') }}
          </div>
        </v-card>
      </v-col>
    </v-row>

    <!-- 二次确认 -->
    <v-dialog v-model="confirmDialog" max-width="520" persistent>
      <v-card>
        <v-card-title class="text-h6">{{ $t('dedup.confirmTitle') }}</v-card-title>
        <v-card-text>
          <div class="text-body-2 mb-2">
            {{ $t('dedup.confirmBody', { n: selectedMerge.length }) }}
          </div>
          <v-alert type="warning" text dense class="text-caption">
            {{ $t('dedup.confirmWarn') }}
          </v-alert>
          <div v-if="doBackup" class="text-caption text--secondary mt-2">
            {{ $t('dedup.confirmBackup') }}
          </div>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn text @click="confirmDialog = false">{{ $t('dedup.cancel') }}</v-btn>
          <v-btn color="success" :loading="applying" @click="doApply">
            {{ $t('dedup.confirmDo') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script>
export default {
  data() {
    return {
      scanning: false,
      scanned: false,
      applying: false,
      doBackup: true,
      groups: [],
      summary: {
        total_groups: 0,
        mergeable: 0,
        skipped: 0,
        will_delete: 0,
        will_move_audio: 0,
      },
      confirmDialog: false,
      resultMsg: "",
      resultFailed: false,
      backupPath: "",
    };
  },
  computed: {
    selectedMerge() {
      return this.groups.filter((g) => g.action === "merge" && g._selected);
    },
  },
  methods: {
    doScan(keepResult = false) {
      this.scanning = true;
      // 合并完的自动重扫要保留结果提示（resultMsg/backupPath）——
      // 否则这里先清空、响应回来再填新 groups，用户根本看不到
      // 「已合并 N 组/备份在哪」就被冲掉了。
      if (!keepResult) {
        this.resultMsg = "";
        this.backupPath = "";
      }
      this.$backend("/admin/book_dedup/scan")
        .then((rsp) => {
          if (rsp.err !== "ok") {
            this.$alert("error", rsp.msg);
            return;
          }
          const plan = rsp.plan || {};
          // 默认全选可合并项（用户可取消勾选）
          this.groups = (plan.groups || []).map((g) => ({ ...g, _selected: g.action === "merge" }));
          this.summary = plan.summary || this.summary;
          this.scanned = true;
        })
        .catch(() => this.$alert("error", this.$t("dedup.scanFailed")))
        .finally(() => {
          this.scanning = false;
        });
    },
    recount() {
      // _selected 变化时 computed 会自动重算，这里只需触发视图
      this.$forceUpdate();
    },
    confirmApply() {
      if (!this.selectedMerge.length) return;
      this.confirmDialog = true;
    },
    doApply() {
      this.applying = true;
      const payload = {
        backup: this.doBackup,
        groups: this.selectedMerge.map((g) => ({
          keep_book_id: g.keep_book_id,
          drop_book_ids: g.drop_book_ids,
        })),
      };
      this.$backend("/admin/book_dedup/apply", {
        method: "POST",
        body: JSON.stringify(payload),
      })
        .then((rsp) => {
          this.confirmDialog = false;
          if (rsp.err !== "ok") {
            this.resultFailed = true;
            this.resultMsg = rsp.msg || this.$t("dedup.applyFailed");
            return;
          }
          this.resultFailed = (rsp.failed || 0) > 0;
          this.resultMsg = rsp.msg;
          this.backupPath = rsp.backup || "";
          // 合并完重新扫一遍，让用户看到剩下的（通常是跳过项）；
          // keepResult=true 保留刚写入的结果提示
          this.doScan(true);
        })
        .catch(() => {
          this.confirmDialog = false;
          this.resultFailed = true;
          this.resultMsg = this.$t("dedup.applyFailed");
        })
        .finally(() => {
          this.applying = false;
        });
    },
  },
};
</script>

<style scoped>
.shrink {
  flex: 0 0 auto;
}
.dedup-mergeable {
  border-left: 3px solid var(--v-success-base);
}
.dedup-skip {
  border-left: 3px solid var(--v-warning-base);
  opacity: 0.85;
}
.dedup-table {
  background: transparent !important;
}
.dedup-table >>> th,
.dedup-table >>> td {
  padding: 4px 8px !important;
  height: auto !important;
}
</style>
