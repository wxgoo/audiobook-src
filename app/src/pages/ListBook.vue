<template>
  <div>
    <v-row>
      <v-col cols=12 class="d-flex align-center">
        <h2>{{ pageDisplayTitle }}</h2>
        <template v-if="isSelectablePage">
          <v-btn icon :color="multiSelectMode ? 'primary' : undefined" class="ml-2"
                 :title="multiSelectMode ? $t('listBook.exitMultiSelect') : $t('listBook.multiSelect')"
                 @click="toggleMultiSelectMode">
            <v-icon>mdi-checkbox-multiple-marked-outline</v-icon>
          </v-btn>
          <v-btn v-if="multiSelectMode && selectedIds.length > 0" icon dark color="red" class="ml-1"
                 :title="$t('listBook.deleteSelected', { count: selectedIds.length })"
                 @click="confirmDialog = true">
            <v-icon>mdi-delete</v-icon>
          </v-btn>
        </template>
        <v-btn v-if="isPrintBooksPage && canUpload" outlined small color="green" class="ml-2"
               :title="$t('listBook.importPrint')" @click="importDialog = true">
          <v-icon small class="mr-1">mdi-file-upload-outline</v-icon>{{ $t('listBook.importPrint') }}
        </v-btn>
        <v-btn v-if="isVisitsPage && books.length > 0" icon class="ml-2"
               :title="$t('listBook.clearVisits')" @click="clearDialog = true">
          <v-icon>mdi-delete-sweep-outline</v-icon>
        </v-btn>
        <v-divider class="mt-3 mb-0"></v-divider>
      </v-col>

      <v-col v-if="isPrintBooksPage && books.length === 0" cols="12" class="text-center grey--text pb-10">
        <v-icon large class="mb-3 d-block">mdi-bookshelf</v-icon>
        {{ $t('listBook.importPrintEmptyHint') }}
      </v-col>

      <v-col>
        <book-cards :books="books" :isAudioPage="isAudioPage" :selectable="multiSelectMode"
                    :selectedIds="selectedIds" @toggle-select="toggleSelect">
          <template v-if="isVisitsPage" v-slot:introduce="{ book }">
            <div v-if="book.visit_time" class="caption grey--text">
              <v-icon x-small>mdi-clock-outline</v-icon> {{ formatVisitTime(book.visit_time) }}
            </div>
          </template>
        </book-cards>
      </v-col>

      <v-col v-if="!books.length && errorText" cols="12" class="text-center pb-8">
        <v-alert type="error" outlined class="text-left">
          {{ errorText }}
        </v-alert>
        <v-btn text color="primary" @click="reload">
          <v-icon small class="mr-1">mdi-refresh</v-icon>{{ $t('listBook.retry') }}
        </v-btn>
      </v-col>

      <v-col v-else-if="!books.length && loaded && !isPrintBooksPage" cols="12" class="text-center grey--text pb-10">
        <v-icon large class="mb-3 d-block">mdi-bookshelf</v-icon>
        {{ $t('listBook.empty') }}
      </v-col>

      <v-col cols=12>
        <v-container class="max-width">
          <v-pagination v-if="page_cnt > 0" v-model="page" :length="page_cnt" circle
                        @input="change_page"></v-pagination>
        </v-container>
        <div class="text-xs-center book-pager">
        </div>
      </v-col>
    </v-row>

    <AppDialog
      v-model="confirmDialog"
      :persistent="false"
      type="confirm"
      :title="$t('listBook.confirmRemoveTitle')"
      color="deep-orange"
      confirm-dark
      max-width="420"
      :dismiss-label="$t('listBook.cancel')"
      :confirm-text="$t('listBook.confirm')"
      :confirm-loading="removing"
      @confirm="removeSelected"
    >
      {{ confirmRemoveContent }}
    </AppDialog>

    <AppDialog
      v-model="clearDialog"
      :persistent="false"
      type="confirm"
      :title="$t('listBook.clearVisitsTitle')"
      color="deep-orange"
      confirm-dark
      max-width="420"
      :confirm-text="$t('listBook.confirm')"
      :confirm-loading="clearing"
      @confirm="clearVisits"
    >
      {{ $t('listBook.clearVisitsContent') }}
    </AppDialog>

    <!-- 实体书 CSV 批量导入对话框 -->
    <AppDialog
      v-model="importDialog"
      type="action"
      :title="$t('listBook.importPrintTitle')"
      icon="mdi-file-upload-outline"
      color="green"
      max-width="520"
      :dismiss-label="$t('listBook.cancel')"
      :confirm-text="$t('listBook.importPrint')"
      confirm-color="green"
      confirm-dark
      :confirm-loading="importing"
      :confirm-disabled="!importFile"
      @confirm="doImportPrintBooks"
    >
      <p class="body-2">{{ $t('listBook.importPrintDesc') }}</p>
      <div class="mb-4">
        <a href="/api/printbooks/import-template" download>
          <v-icon small>mdi-download</v-icon>{{ $t('listBook.importPrintDownloadTpl') }}
        </a>
      </div>
      <input ref="csvInput" type="file" accept=".csv,text/csv" style="display: none" @change="onCsvSelected" />
      <v-btn outlined color="green" block @click="$refs.csvInput.click()">
        <v-icon small class="mr-1">mdi-paperclip</v-icon>
        {{ importFile ? importFile.name : $t('listBook.importPrintPickCsv') }}
      </v-btn>
      <v-alert v-if="importErrors.length" type="warning" dense class="mt-4" style="font-size: 13px;">
        <div style="max-height: 160px; overflow-y: auto;">
          <div v-for="(e, i) in importErrors" :key="i">{{ e }}</div>
        </div>
      </v-alert>
    </AppDialog>
  </div>
</template>

<script>
import BookCards from "../components/BookCards.vue";
import { clampPageSize } from "~/utils/pageSize";

const SELECTABLE_ACTIONS = {
  '/favorites': 'favorite',
  '/wants': 'wants',
  '/reading': 'reading',
  '/read-done': 'read-done',
};

export default {
  components: {
    BookCards,
  },
  computed: {
    page_size() {
      if (process.client) {
        const stored = localStorage.getItem('defaultPageSize');
        if (stored) {
          return clampPageSize(stored, 60);
        }
      }
      return clampPageSize(this.$store?.state?.default_page_size, 60);
    },
    pageDisplayTitle() {
      return this.getPageTitle();
    },
    isVisitsPage() {
      return this.$route.path === '/visits';
    },
    isPrintBooksPage() {
      return this.$route.path === '/printbooks';
    },
    canUpload() {
      // 上传能力看后端下发的 user.can_upload（由用户 u 权限位决定，管理员恒 true）。
      // 不能用 sys.allow.upload——那只是「访客能否上传」，站点开了必须登录后它恒为 false，
      // 拿它判断会把已登录用户的可上传状态判错。
      const u = this.$store.state.user;
      return !!(u && u.is_login && (u.can_upload || u.is_admin));
    },
    isSelectablePage() {
      return Object.prototype.hasOwnProperty.call(SELECTABLE_ACTIONS, this.$route.path);
    },
    errorText() {
      if (this.load_error) {
        return this.load_error;
      }
      if (this.err && this.err !== 'ok') {
        return this.msg || this.$t('listBook.loadFailed');
      }
      return '';
    },
    confirmRemoveContent() {
      const action = SELECTABLE_ACTIONS[this.$route.path];
      const keys = {
        favorite: 'listBook.confirmRemoveContentFavorites',
        wants: 'listBook.confirmRemoveContentWants',
        reading: 'listBook.confirmRemoveContentReading',
        'read-done': 'listBook.confirmRemoveContentReadDone',
      };
      return this.$t(keys[action] || 'listBook.confirmRemoveContentFavorites', { count: this.selectedIds.length });
    },
  },
  data: () => ({
    title: "",
    page: 1,
    books: [],
    total: 0,
    page_cnt: 0,
    inited: false,
    loaded: false,
    ssr_loaded: false,
    load_error: "",
    isAudioPage: false,
    multiSelectMode: false,
    selectedIds: [],
    confirmDialog: false,
    removing: false,
    clearDialog: false,
    clearing: false,
    importDialog: false,
    importing: false,
    importFile: null,
    importErrors: [],
  }),
  async asyncData({route, app, res}) {
    if (res !== undefined) {
      res.setHeader('Cache-Control', 'no-cache');
    }
    const rsp = await app.$backend(route.fullPath, { timeout: 20000 });
    // 只有「服务端真的取到数据」才标记，避免把构建期的空结果当成已加载：
    // 静态产物里的 asyncData 只在构建时跑一次，运行时首屏不会重跑（见 mounted）。
    if (rsp && rsp.err === 'ok') {
      return Object.assign({}, rsp, { ssr_loaded: true });
    }
    return rsp || {};
  },
  head() {
    return {
      title: this.getPageTitle(),
    }
  },
  created() {
    if (this.$route.query.start != undefined) {
      this.page = 1 + parseInt(this.$route.query.start / this.page_size)
    }
    this.page_cnt = Math.max(1, Math.ceil(this.total / this.page_size))

    this.loaded = true;
    this.checkIfAudioPage();
  },
  mounted() {
    // 首屏直入 / 强刷：静态产物里 asyncData 只在构建期执行，运行时不会重跑，
    // 没有这段就不会发出任何取书请求（页面壳正常、网格空白、Console 干净）。
    // ssr_loaded 为真表示服务端已取到数据（nuxt dev / SSR 部署），不再重复请求；
    // 同组件内切路由/翻页仍走 beforeRouteUpdate → init，由请求令牌去重。
    if (!this.ssr_loaded && !this.inited) {
      this.init(this.$route);
    }
  },

  beforeRouteUpdate(to, from, next) {
    this.init(to, next);
  },
  methods: {
    getPageTitle() {
      let displayTitle = "";

      switch (this.$route.path) {
        case "/hot":
          displayTitle = this.$t('listBook.hotBooks');
          break;

        case "/search":
          displayTitle = this.$t('listBook.search');
          break;

        case "/all":
          displayTitle = this.$t('listBook.allBooks');
          break;

        case "/favorites":
          displayTitle = this.$t('listBook.favoritesBooks');
          break;

        case "/visits":
          displayTitle = this.$t('listBook.visitsBooks');
          break;

        case "/wants":
          displayTitle = this.$t('listBook.wantsBooks');
          break;

        case "/reading":
          displayTitle = this.$t('listBook.readingBooks');
          break;

        case "/read-done":
          displayTitle = this.$t('listBook.readDoneBooks');
          break;

        case "/printbooks":
          displayTitle = this.$t('listBook.physicalBooks');
          break;

        case "/audiobooks":
          displayTitle = this.$t('listBook.audioBooks');
          break;

        case "/soledbooks":
          displayTitle = this.$t('listBook.soledBooks');
          break;

        default:
          if (this.$route.params.meta !== undefined) {
            var name = decodeURIComponent(this.$route.params.name);
            var titles = {
              tag: this.$t('listBook.tagBooks', { name }),
              series: this.$t('listBook.seriesBooks', { name }),
              rating: this.$t('listBook.ratingBooks', { name }),
              author: this.$t('listBook.authorBooks', { name }),
              publisher: this.$t('listBook.publisherBooks', { name }),
              favorites: this.$t('listBook.favoritesBooks', { name }),
              wants: this.$t('listBook.wantsBooks', { name }),
              reading: this.$t('listBook.readingBooks', { name }),
              readDone: this.$t('listBook.readDoneBooks', { name }),
            }
            var meta = this.$route.path.split("/")[1];
            if (titles[meta] !== undefined) {
              displayTitle = titles[meta];
            }
          }

          if (!displayTitle) {
            displayTitle = this.title;
          }
          break;
      }

      return displayTitle;
    },
    checkIfAudioPage() {
      this.isAudioPage = this.$route.path === '/audiobooks';
    },
    init(route, next) {
      this.inited = true;
      this.loaded = true;
      this.$store.commit('navbar', true);

      this.isAudioPage = route.path === '/audiobooks';

      // 同一组件内切页/切筛选会重复进入这里，用递增令牌丢弃过期响应，
      // 避免先发后到的旧请求覆盖新页数据（表现为“有时正常有时空白”）。
      const token = (this._reqToken || 0) + 1;
      this._reqToken = token;
      const reqPath = route.fullPath;

      this.$backend(reqPath, { timeout: 20000 })
        .then(rsp => {
          if (token !== this._reqToken || this.$route.fullPath !== reqPath) {
            return;
          }
          if (rsp.err != 'ok') {
            this.books = [];
            this.total = 0;
            this.page_cnt = 1;
            this.load_error = rsp.msg || this.$t('listBook.loadFailed');
            this.$alert("error", this.load_error);
            return;
          }
          this.load_error = "";
          this.err = "ok";
          this.msg = "";
          this.title = rsp.title;
          this.books = rsp.books;
          this.total = rsp.total
          this.page_cnt = Math.max(1, Math.ceil(this.total / this.page_size));
        })
        .catch(() => {
          if (token !== this._reqToken) {
            return;
          }
          this.books = [];
          this.total = 0;
          this.page_cnt = 1;
          this.load_error = this.$t('listBook.loadFailed');
          this.$alert("error", this.load_error);
        })
      if (next) next();
    },
    reload() {
      this.init(this.$route);
    },
    change_page() {
      var r = Object.assign({}, this.$route.query);
      if (this.page < 1) {
        this.page = 1
      }
      r.start = (this.page - 1) * this.page_size;
      r.size = this.page_size;
      this.$router.push({query: r});
    },
    toggleMultiSelectMode() {
      this.multiSelectMode = !this.multiSelectMode;
      if (!this.multiSelectMode) {
        this.selectedIds = [];
      }
    },
    toggleSelect(bookId) {
      const idx = this.selectedIds.indexOf(bookId);
      if (idx === -1) {
        this.selectedIds = [...this.selectedIds, bookId];
      } else {
        this.selectedIds = this.selectedIds.filter((id) => id !== bookId);
      }
    },
    formatVisitTime(value) {
      const date = new Date(value);
      return Number.isNaN(date.getTime()) ? '' : date.toLocaleString();
    },
    onCsvSelected(event) {
      const f = (event.target.files || [])[0];
      event.target.value = '';
      if (!f) return;
      if (!/\.csv$/i.test(f.name)) {
        this.$alert('error', this.$t('listBook.importPrintNoFile'));
        return;
      }
      this.importFile = f;
      this.importErrors = [];
    },
    async doImportPrintBooks() {
      if (this.importing || !this.importFile) return;
      this.importing = true;
      this.importErrors = [];
      try {
        const data = new FormData();
        data.append('csvfile', this.importFile, this.importFile.name);
        const rsp = await this.$backend('/printbooks/import', { method: 'POST', body: data });
        if (rsp.err !== 'ok') {
          this.$alert('error', rsp.msg || this.$t('listBook.importPrintFailed'));
          return;
        }
        this.importErrors = rsp.errors || [];
        this.$alert('success', rsp.msg || this.$t('listBook.importPrintSuccess'));
        if ((rsp.ok_count || 0) > 0) {
          this.importDialog = false;
          this.importFile = null;
          this.init(this.$route);
        } else if (!this.importErrors.length) {
          this.importDialog = false;
        }
      } catch (e) {
        this.$alert('error', this.$t('listBook.importPrintFailed'));
      } finally {
        this.importing = false;
      }
    },
    async clearVisits() {
      if (this.clearing) return;
      this.clearing = true;
      try {
        const rsp = await this.$backend('/visits/clear', { method: 'POST' });
        if (rsp.err === 'ok') {
          this.books = [];
          this.total = 0;
          this.page_cnt = 1;
          this.clearDialog = false;
          this.$alert('success', this.$t('listBook.clearVisitsSuccess'));
        } else {
          this.$alert('error', rsp.msg || this.$t('listBook.removeFailed'));
        }
      } catch (e) {
        this.$alert('error', this.$t('listBook.removeFailed'));
      } finally {
        this.clearing = false;
      }
    },
    async removeSelected() {
      if (this.removing || this.selectedIds.length === 0) return;
      const action = SELECTABLE_ACTIONS[this.$route.path];
      if (!action) return;
      this.removing = true;
      try {
        const rsp = await this.$backend('/books/batch-remove-state', {
          method: 'POST',
          body: JSON.stringify({ book_ids: this.selectedIds, action }),
        });
        if (rsp.err === 'ok') {
          const removedIds = new Set(this.selectedIds);
          this.books = this.books.filter((b) => !removedIds.has(b.id));
          this.total = Math.max(0, this.total - removedIds.size);
          this.page_cnt = Math.max(1, Math.ceil(this.total / this.page_size));
          this.$alert('success', this.$t('listBook.removeSuccess', { count: removedIds.size }));
          this.selectedIds = [];
          this.confirmDialog = false;
          this.multiSelectMode = false;
        } else {
          this.$alert('error', rsp.msg || this.$t('listBook.removeFailed'));
        }
      } catch (e) {
        this.$alert('error', this.$t('listBook.removeFailed'));
      } finally {
        this.removing = false;
      }
    },
  },
}
</script>

<style scoped>
.book-list-legend {
  margin-top: 6px;
  margin-bottom: 16px;
}

.book-pager {
  margin-top: 30px;
}
</style>
