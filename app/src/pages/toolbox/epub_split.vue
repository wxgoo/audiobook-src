<template>
  <v-container fluid class="pa-4">
    <!-- Page header -->
    <v-row class="mb-3" align="center">
      <v-col class="text-center">
        <span class="text-h5 font-weight-bold">{{ $t('epubSplit.title') }}</span>
      </v-col>
      <v-col cols="auto">
        <v-btn small color="error" @click="$router.go(-1)">
          <v-icon small left>mdi-close</v-icon>{{ $t('epubSplit.close') }}
        </v-btn>
      </v-col>
    </v-row>

    <!-- Main card -->
    <v-row justify="center">
      <v-col cols="12" md="9" lg="7">
        <v-card rounded="xl" outlined class="es-card pa-6">
          <!-- 模式切换：手动选章节 / 自动识别分册 -->
          <v-row class="mb-4" justify="center">
            <v-btn-toggle v-model="mode" mandatory color="primary" dense rounded>
              <v-btn :value="'manual'" small>
                <v-icon small left>mdi-content-cut</v-icon>{{ $t('epubSplit.modeManual') }}
              </v-btn>
              <v-btn :value="'auto'" small>
                <v-icon small left>mdi-auto-fix</v-icon>{{ $t('epubSplit.modeAuto') }}
              </v-btn>
            </v-btn-toggle>
          </v-row>

          <v-alert type="warning" dense text rounded="lg" class="mb-5">
            {{ mode === 'auto' ? $t('epubSplit.autoHint') : $t('epubSplit.hint') }}
          </v-alert>

          <!-- Search field -->
          <v-text-field
            v-model="query"
            :label="$t('epubSplit.searchPlaceholder')"
            :loading="searching"
            outlined
            dense
            clearable
            hide-details
            class="mb-3"
            prepend-inner-icon="mdi-magnify"
            append-outer-icon="mdi-magnify"
            @keyup.enter="search"
            @click:append-outer="search"
            @click:clear="clearSearch"
          />

          <!-- Book list -->
          <div class="es-book-list mb-4">
            <div v-if="searching" class="text-center py-6">
              <v-progress-circular indeterminate color="primary" size="32" />
            </div>
            <div v-else-if="books.length === 0 && searched" class="text-center py-4 grey--text">
              {{ $t('epubSplit.noResults') }}
            </div>
            <v-list v-else-if="books.length > 0" dense class="es-list pa-0">
              <v-list-item
                v-for="book in books"
                :key="book.id"
                :class="['es-book-item', { 'es-book-selected': selected && selected.id === book.id }]"
                @click="selectBook(book)"
              >
                <v-list-item-avatar tile size="44" class="mr-3">
                  <v-img :src="book.thumb" :alt="book.title">
                    <template #error>
                      <v-icon color="grey lighten-1">mdi-book-outline</v-icon>
                    </template>
                  </v-img>
                </v-list-item-avatar>
                <v-list-item-content>
                  <v-list-item-title class="es-book-title">{{ book.title }}</v-list-item-title>
                  <v-list-item-subtitle class="es-book-author">{{ (book.authors || []).join(', ') }}</v-list-item-subtitle>
                  <div class="mt-1">
                    <v-chip
                      v-for="file in (book.files || [])"
                      :key="file.format"
                      x-small
                      :color="file.format === 'EPUB' ? 'primary' : 'default'"
                      outlined
                      class="mr-1"
                    >{{ file.format }}</v-chip>
                  </div>
                </v-list-item-content>
                <v-list-item-action v-if="selected && selected.id === book.id">
                  <v-icon color="primary">mdi-check-circle</v-icon>
                </v-list-item-action>
              </v-list-item>
            </v-list>
          </div>

          <!-- ============ 手动模式：章节选择 ============ -->
          <template v-if="mode === 'manual'">
            <template v-if="selected">
              <div v-if="chaptersLoading" class="text-center py-6">
                <v-progress-circular indeterminate color="primary" size="32" />
              </div>
              <template v-else-if="chapters.length > 0">
                <v-row align="center" class="mb-1" no-gutters>
                  <v-col>
                    <span class="text-subtitle-2 font-weight-bold">
                      {{ $t('epubSplit.chaptersTitle') }} ({{ selectedChapters.length }}/{{ chapters.length }})
                    </span>
                  </v-col>
                  <v-col cols="auto">
                    <v-btn x-small text color="primary" :disabled="selectedChapters.length === 0" @click="clearChapterSelection">
                      <v-icon x-small left>mdi-broom</v-icon>{{ $t('epubSplit.clearSelection') }}
                    </v-btn>
                  </v-col>
                </v-row>
                <div class="es-chapter-list mb-4">
                  <v-checkbox
                    v-for="(chapter, index) in chapters"
                    :key="chapter.num"
                    :input-value="selectedChapters.includes(chapter.num)"
                    :label="chapter.title"
                    :title="chapter.preview"
                    dense
                    hide-details
                    class="es-chapter-item"
                    @click.native.capture="onChapterClick($event, chapter, index)"
                  />
                </div>
              </template>
              <div v-else-if="chaptersErrorMsg" class="text-center py-4">
                <v-alert type="error" dense text rounded="lg">{{ chaptersErrorMsg }}</v-alert>
              </div>
            </template>

            <!-- Cover option -->
            <v-checkbox
              v-if="chapters.length > 0"
              v-model="useFirstChapterCover"
              :label="$t('epubSplit.useFirstChapterCoverLabel')"
              dense
              hide-details
              class="mt-0 mb-2"
            />

            <!-- Generate button -->
            <div v-if="chapters.length > 0" class="d-flex justify-center">
              <v-btn
                color="primary"
                class="es-start-btn"
                :loading="processing"
                :disabled="processing || selectedChapters.length === 0"
                @click="generateBook"
              >
                <v-icon left>mdi-content-cut</v-icon>
                {{ $t('epubSplit.generateBtn') }}
              </v-btn>
            </div>

            <!-- Result -->
            <transition name="es-fade">
              <div v-if="resultBook" class="text-center mt-4">
                <v-alert type="success" dense text rounded="lg">
                  {{ $t('epubSplit.generateSuccess') }}
                  <a :href="'/book/' + resultBook.book_id" target="_blank" class="font-weight-bold">{{ resultBook.title }}</a>
                </v-alert>
              </div>
            </transition>
          </template>

          <!-- ============ 自动模式：合集分册识别 ============ -->
          <template v-else>
            <!-- 检测状态 -->
            <div v-if="selected">
              <v-alert v-if="autoErrorMsg" type="error" dense text rounded="lg" class="mb-4">{{ autoErrorMsg }}</v-alert>
              <v-row align="center" class="mb-3" no-gutters>
                <v-col>
                  <span class="text-subtitle-2 font-weight-bold">{{ selected.title }}</span>
                  <div class="text-caption grey--text">{{ selMeta }}</div>
                </v-col>
                <v-col cols="auto">
                  <v-btn x-small text color="primary" :loading="detecting" @click="detect(selected.id)">
                    <v-icon x-small left>mdi-refresh</v-icon>{{ $t('epubSplit.redetect') }}
                  </v-btn>
                </v-col>
              </v-row>

              <div v-if="detecting" class="text-center py-6">
                <v-progress-circular indeterminate color="primary" size="32" />
                <div class="text-caption grey--text mt-2">{{ $t('epubSplit.detecting') }}</div>
              </div>

              <!-- 分册微调列表 -->
              <template v-else-if="volumes.length > 0">
                <v-row align="center" class="mb-2" no-gutters>
                  <v-col><span class="text-subtitle-2 font-weight-bold">{{ $t('epubSplit.volumesTitle') }} ({{ volumes.length }})</span></v-col>
                </v-row>
                <div class="es-vol-list mb-4">
                  <div v-for="(vol, i) in volumes" :key="i" class="es-vol">
                    <div class="d-flex align-center flex-wrap">
                      <v-avatar size="26" color="primary" class="mr-2 white--text font-weight-bold">{{ i + 1 }}</v-avatar>
                      <v-text-field
                        v-model="vol.name"
                        :label="$t('epubSplit.volumeName')"
                        dense hide-details outlined class="es-vol-name"
                      />
                      <v-chip x-small class="ml-2" :color="vol.confidence >= 0.85 ? 'success' : 'warning'" text-color="white">
                        {{ vol.confidence }} {{ $t('epubSplit.confidence') }}
                      </v-chip>
                      <v-spacer />
                      <v-btn x-small text color="primary" v-if="i > 0" @click="mergeVolume(i)" :title="$t('epubSplit.mergePrev')">
                        <v-icon x-small>mdi-arrow-left-bold</v-icon>{{ $t('epubSplit.mergePrev') }}
                      </v-btn>
                      <v-btn x-small text color="error" @click="deleteVolume(i)" :title="$t('epubSplit.deleteVolume')">
                        <v-icon x-small>mdi-delete</v-icon>{{ $t('epubSplit.deleteVolume') }}
                      </v-btn>
                    </div>
                    <div class="d-flex align-center flex-wrap mt-2 es-vol-range">
                      <span class="text-caption grey--text mr-2">{{ $t('epubSplit.rangeStart') }}</span>
                      <v-select v-model="vol.start" :items="chapterItems" dense hide-details outlined class="es-vol-select" />
                      <span class="text-caption grey--text mx-2">{{ $t('epubSplit.rangeEnd') }}</span>
                      <v-select v-model="vol.end" :items="chapterItems" dense hide-details outlined class="es-vol-select" />
                      <span class="text-caption grey--text ml-2">({{ Math.max(0, vol.end - vol.start + 1) }})</span>
                    </div>
                    <div class="es-vol-tags mt-2" v-if="vol.titles && vol.titles.length">
                      <v-chip x-small outlined v-for="(t, ti) in vol.titles.slice(0, 5)" :key="ti" class="mr-1 mb-1">{{ t }}</v-chip>
                    </div>
                  </div>
                </div>

                <v-checkbox
                  v-model="useVolCover"
                  :label="$t('epubSplit.useVolCover')"
                  dense hide-details class="mt-0 mb-3"
                />

                <div class="d-flex justify-center">
                  <v-btn color="primary" class="es-start-btn" :loading="batching" :disabled="batching" @click="batchSplit">
                    <v-icon left>mdi-auto-fix</v-icon>{{ $t('epubSplit.batchBtn') }}
                  </v-btn>
                </div>

                <!-- 批量结果 -->
                <transition name="es-fade">
                  <div v-if="batchResult" class="mt-4">
                    <v-alert :type="batchResult.failed ? 'info' : 'success'" dense text rounded="lg">
                      {{ $t('epubSplit.batchSuccess', { n: batchResult.succeeded }) }}
                      <span v-if="batchResult.failed"> · {{ $t('epubSplit.batchFailed', { n: batchResult.failed }) }}</span>
                    </v-alert>
                    <div class="es-result-list">
                      <div v-for="(r, ri) in batchResult.results" :key="ri" class="es-result-item" :class="r.ok ? 'ok' : 'fail'">
                        <template v-if="r.ok">
                          <v-icon small color="success">mdi-check-circle</v-icon>
                          <a :href="'/book/' + r.book_id" target="_blank">{{ r.name }}</a>
                        </template>
                        <template v-else>
                          <v-icon small color="error">mdi-close-circle</v-icon>
                          <span>{{ r.name }} — {{ r.error }}</span>
                        </template>
                      </div>
                    </div>
                  </div>
                </transition>
              </template>

              <div v-else-if="!detecting && detectDone" class="text-center py-4 grey--text">
                {{ $t('epubSplit.noVolume') }}
              </div>
            </div>
          </template>

          <!-- 通用错误提示（手动/自动共用） -->
          <transition name="es-fade">
            <v-alert v-if="mode === 'manual' && errorMsg" type="error" dense text rounded="lg" class="mb-4">{{ errorMsg }}</v-alert>
          </transition>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script>
export default {
  data: () => ({
    mode: 'manual',

    // 搜索 / 选书（两种模式共用）
    query: '',
    books: [],
    searching: false,
    searched: false,
    selected: null,

    // 手动模式
    chaptersLoading: false,
    chapters: [],
    selectedChapters: [],
    lastClickedChapterIndex: null,
    chaptersErrorMsg: '',
    useFirstChapterCover: false,
    processing: false,
    errorMsg: '',
    resultBook: null,

    // 自动分册模式
    autoChapters: [],
    volumes: [],
    detecting: false,
    detectDone: false,
    batching: false,
    autoErrorMsg: '',
    selMeta: '',
    batchResult: null,
    useVolCover: true,
    diagnostics: {},
  }),
  computed: {
    chapterItems() {
      return this.autoChapters.map((c) => ({ text: c.title, value: c.num }));
    },
  },
  created() {
    this.$store.commit('navbar', true);
  },
  watch: {
    mode() {
      this.resetSelection();
    },
  },
  methods: {
    async search() {
      const q = (this.query || '').trim();
      if (!q) return;
      this.searching = true;
      this.searched = false;
      this.resetSelection();
      try {
        const rsp = await this.$backend(`/search?title=title:${encodeURIComponent(q)}`);
        this.books = rsp.err === 'ok' ? (rsp.books || []) : [];
      } catch (_e) {
        this.books = [];
      } finally {
        this.searching = false;
        this.searched = true;
      }
    },
    clearSearch() {
      this.books = [];
      this.searched = false;
      this.resetSelection();
    },
    resetSelection() {
      this.selected = null;
      // 手动
      this.chapters = [];
      this.selectedChapters = [];
      this.lastClickedChapterIndex = null;
      this.chaptersErrorMsg = '';
      this.errorMsg = '';
      this.resultBook = null;
      this.useFirstChapterCover = false;
      // 自动
      this.autoChapters = [];
      this.volumes = [];
      this.detecting = false;
      this.detectDone = false;
      this.batching = false;
      this.autoErrorMsg = '';
      this.selMeta = '';
      this.batchResult = null;
      this.diagnostics = {};
    },
    async selectBook(book) {
      if (this.selected && this.selected.id === book.id) {
        this.resetSelection();
        return;
      }
      this.resetSelection();
      this.selected = book;
      if (!(book.files || []).some((f) => f.format === 'EPUB')) {
        if (this.mode === 'auto') this.autoErrorMsg = this.$t('epubSplit.noEpub');
        else this.chaptersErrorMsg = this.$t('epubSplit.noEpub');
        return;
      }
      if (this.mode === 'auto') {
        await this.detect(book.id);
      } else {
        await this.loadChapters();
      }
    },

    // ---------- 手动模式 ----------
    async loadChapters() {
      this.chaptersLoading = true;
      this.chaptersErrorMsg = '';
      try {
        const rsp = await this.$backend('/toolbox/epub_split/chapters', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ book_id: this.selected.id }),
        });
        if (rsp.err === 'ok') {
          this.chapters = (rsp.data && rsp.data.chapters) || [];
        } else {
          this.chaptersErrorMsg = rsp.msg || rsp.err;
        }
      } catch (e) {
        this.chaptersErrorMsg = String(e);
      } finally {
        this.chaptersLoading = false;
      }
    },
    clearChapterSelection() {
      this.selectedChapters = [];
      this.lastClickedChapterIndex = null;
    },
    onChapterClick(event, chapter, index) {
      event.preventDefault();
      event.stopPropagation();
      if (event.shiftKey && this.lastClickedChapterIndex !== null) {
        const start = Math.min(this.lastClickedChapterIndex, index);
        const end = Math.max(this.lastClickedChapterIndex, index);
        const rangeNums = this.chapters.slice(start, end + 1).map((c) => c.num);
        const merged = new Set(this.selectedChapters);
        rangeNums.forEach((num) => merged.add(num));
        this.selectedChapters = this.chapters.map((c) => c.num).filter((num) => merged.has(num));
      } else {
        const idx = this.selectedChapters.indexOf(chapter.num);
        if (idx === -1) {
          this.selectedChapters = [...this.selectedChapters, chapter.num];
        } else {
          this.selectedChapters = this.selectedChapters.filter((num) => num !== chapter.num);
        }
      }
      this.lastClickedChapterIndex = index;
    },
    async generateBook() {
      if (this.selectedChapters.length === 0) return;
      this.errorMsg = '';
      this.resultBook = null;
      this.processing = true;
      try {
        const rsp = await this.$backend('/toolbox/epub_split/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            book_id: this.selected.id,
            chapters: this.selectedChapters,
            use_first_chapter_cover: this.useFirstChapterCover,
          }),
        });
        if (rsp.err === 'ok') {
          this.resultBook = rsp.data;
        } else {
          this.errorMsg = rsp.msg || rsp.err;
        }
      } catch (e) {
        this.errorMsg = String(e);
      } finally {
        this.processing = false;
      }
    },

    // ---------- 自动分册模式 ----------
    async detect(bookId) {
      if (!bookId) return;
      this.detecting = true;
      this.detectDone = false;
      this.autoErrorMsg = '';
      this.volumes = [];
      this.batchResult = null;
      try {
        const rsp = await this.$backend('/toolbox/epub_split/detect', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ book_id: bookId }),
        });
        if (rsp.err === 'ok') {
          const d = rsp.data || {};
          this.autoChapters = d.chapters || [];
          this.volumes = (d.volumes || []).map((v) => ({
            name: v.name,
            start: v.start,
            end: v.end,
            confidence: v.confidence || 0,
            titles: v.titles || [],
          }));
          this.diagnostics = d.diagnostics || {};
          this.selMeta = (d.authors || []).join('、') + (d.total_chapters ? ' · ' + d.total_chapters + ' 章节节点' : '');
          this.detectDone = true;
        } else {
          this.autoErrorMsg = rsp.msg || rsp.err;
        }
      } catch (e) {
        this.autoErrorMsg = String(e);
      } finally {
        this.detecting = false;
      }
    },
    deleteVolume(i) {
      if (this.volumes.length <= 1) return;
      this.volumes.splice(i, 1);
      this.batchResult = null;
    },
    mergeVolume(i) {
      if (i <= 0 || i >= this.volumes.length) return;
      const prev = this.volumes[i - 1];
      const cur = this.volumes[i];
      prev.end = Math.max(prev.end, cur.end);
      if (cur.start < prev.start) prev.start = cur.start;
      this.volumes.splice(i, 1);
      this.batchResult = null;
    },
    async batchSplit() {
      if (!this.selected || !this.volumes.length) return;
      // 校验范围
      for (let i = 0; i < this.volumes.length; i++) {
        const v = this.volumes[i];
        if (v.end < v.start) {
          this.autoErrorMsg = (this.$t('epubSplit.volumeName') + ' #' + (i + 1)) + ': ' + this.$t('epubSplit.badRange');
          return;
        }
      }
      this.autoErrorMsg = '';
      this.batching = true;
      this.batchResult = null;
      try {
        const rsp = await this.$backend('/toolbox/epub_split/batch', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            book_id: this.selected.id,
            volumes: this.volumes.map((v) => ({ name: v.name, start: v.start, end: v.end })),
            use_chapter_cover: this.useVolCover,
          }),
        });
        if (rsp.err === 'ok') {
          this.batchResult = rsp.data;
        } else {
          this.autoErrorMsg = rsp.msg || rsp.err;
        }
      } catch (e) {
        this.autoErrorMsg = String(e);
      } finally {
        this.batching = false;
      }
    },
  },
};
</script>

<style scoped>
.es-card {
  border: 2px solid #90CAF9;
}

.es-book-list {
  max-height: 280px;
  overflow-y: auto;
}

.es-list {
  background: transparent !important;
}

.es-book-item {
  border-radius: 8px !important;
  margin-bottom: 4px;
  cursor: pointer;
  transition: background 0.15s;
}

.es-book-item:hover {
  background: rgba(144, 202, 249, 0.15) !important;
}

.es-book-selected {
  background: rgba(144, 202, 249, 0.25) !important;
  border: 1px solid #90CAF9;
}

.es-book-title {
  font-size: 13px !important;
  white-space: normal !important;
  line-height: 1.3;
}

.es-book-author {
  font-size: 11px !important;
}

.es-chapter-list {
  max-height: 320px;
  overflow-y: auto;
  border: 1px solid rgba(0, 0, 0, 0.12);
  border-radius: 8px;
  padding: 8px 12px;
}

.es-chapter-item {
  cursor: help;
}

.es-start-btn {
  width: 60%;
  min-width: 200px;
}

/* 自动分册模式 */
.es-vol-list {
  max-height: 420px;
  overflow-y: auto;
}
.es-vol {
  border: 1px solid rgba(0, 0, 0, 0.12);
  border-radius: 10px;
  padding: 10px 12px;
  margin-bottom: 10px;
}
.es-vol-name {
  flex: 1;
  min-width: 160px;
}
.es-vol-range {
  padding-left: 34px;
}
.es-vol-select {
  max-width: 240px;
  font-size: 12px;
}
.es-vol-tags {
  padding-left: 34px;
}
.es-result-list {
  display: grid;
  gap: 6px;
  max-height: 260px;
  overflow-y: auto;
}
.es-result-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.04);
  font-size: 13px;
}
.es-result-item.ok a {
  font-weight: 600;
}

.es-fade-enter-active,
.es-fade-leave-active {
  transition: opacity 0.3s, transform 0.25s;
}
.es-fade-enter,
.es-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
