<template>
  <v-container fluid class="pa-4">
    <!-- 页头 -->
    <v-row class="mb-3" align="center">
      <v-col>
        <span class="text-h5 font-weight-bold">{{ $t('takedown.pageTitle') }}</span>
        <div class="text-caption grey--text mt-1">{{ $t('takedown.pageSubtitle') }}</div>
      </v-col>
      <v-col cols="auto">
        <v-btn small color="primary" :loading="loading" @click="load">
          <v-icon small left>mdi-refresh</v-icon>{{ $t('takedown.refresh') }}
        </v-btn>
        <v-btn small color="warning" class="ml-2" @click="openAdd">
          <v-icon small left>mdi-plus</v-icon>{{ $t('takedown.add') }}
        </v-btn>
      </v-col>
    </v-row>

    <!-- 当前声明文案 -->
    <v-alert type="warning" outlined class="mb-4">
      <div class="text-subtitle-2 font-weight-bold">{{ $t('takedown.noticeTitle') }}</div>
      <div class="text-body-2 mt-1">{{ notice || defaultNotice }}</div>
      <div class="text-caption mt-2">{{ $t('takedown.noticeHint') }}</div>
    </v-alert>

    <v-card outlined>
      <v-card-title class="text-subtitle-1">
        <v-icon small left color="warning">mdi-copyright</v-icon>{{ $t('takedown.listTitle') }}
        <v-spacer></v-spacer>
        <span class="text-caption grey--text">{{ $t('takedown.total', { n: items.length }) }}</span>
      </v-card-title>
      <v-divider></v-divider>
      <v-data-table
        :headers="headers"
        :items="items"
        :loading="loading"
        item-key="book_id"
        v-model="selected"
        show-select
        :items-per-page="20"
        :no-data-text="$t('takedown.empty')"
        :no-results-text="$t('takedown.empty')"
      >
        <template v-slot:item.title="{ item }">
          <a :href="'/book/' + item.book_id" target="_blank">
            {{ item.title || ('#' + item.book_id) }}
          </a>
          <span class="text-caption grey--text ml-1">#{{ item.book_id }}</span>
        </template>
        <template v-slot:item.reason="{ item }">
          <span class="text-body-2">{{ item.reason || '—' }}</span>
        </template>
        <template v-slot:item.create_time="{ item }">
          <span class="text-caption">{{ formatTime(item.create_time) }}</span>
        </template>
        <template v-slot:item.actions="{ item }">
          <v-btn small text color="primary" :loading="submitting" @click="restore([item.book_id])">
            <v-icon small left>mdi-lock-open-outline</v-icon>{{ $t('takedown.restore') }}
          </v-btn>
        </template>
      </v-data-table>
      <v-card-actions v-if="selected.length">
        <span class="text-caption ml-2">{{ $t('takedown.selected', { n: selected.length }) }}</span>
        <v-spacer></v-spacer>
        <v-btn small color="primary" :loading="submitting" @click="restore(selected.map(x => x.book_id))">
          <v-icon small left>mdi-lock-open-outline</v-icon>{{ $t('takedown.batchRestore') }}
        </v-btn>
      </v-card-actions>
    </v-card>

    <!-- 新增下架 -->
    <v-dialog v-model="dialog_add" max-width="500" persistent>
      <v-card class="dialog-border">
        <v-toolbar flat dense dark color="warning">
          <v-icon left>mdi-copyright</v-icon>
          <v-toolbar-title>{{ $t('takedown.add') }}</v-toolbar-title>
          <v-spacer></v-spacer>
          <v-btn icon small @click="dialog_add = false"><v-icon>mdi-close</v-icon></v-btn>
        </v-toolbar>
        <v-card-text class="pt-5">
          <div class="text-body-2 mb-4">{{ $t('takedown.addHint') }}</div>
          <v-text-field v-model="form_book_id" :label="$t('takedown.bookId')"
                        :hint="$t('takedown.bookIdHint')" persistent-hint dense outlined
                        type="number" min="1"></v-text-field>
          <v-textarea v-model="form_reason" :label="$t('takedown.reason')"
                      :hint="$t('takedown.reasonHint')" rows="3" outlined dense
                      persistent-hint counter="2000" maxlength="2000" class="mt-3"></v-textarea>
          <div class="text-caption mt-3">{{ notice || defaultNotice }}</div>
        </v-card-text>
        <v-card-actions class="justify-end px-4 pb-4">
          <v-btn text @click="dialog_add = false">{{ $t('common.cancel') }}</v-btn>
          <v-btn color="warning" :loading="submitting" @click="submitAdd">
            {{ $t('takedown.confirmAdd') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script>
export default {
  data: () => ({
    items: [],
    selected: [],
    notice: '',
    defaultNotice: '',
    loading: false,
    submitting: false,
    dialog_add: false,
    form_book_id: '',
    form_reason: '',
  }),
  computed: {
    headers() {
      return [
        { text: this.$t('takedown.colBook'), value: 'title' },
        { text: this.$t('takedown.colReason'), value: 'reason' },
        { text: this.$t('takedown.colOperator'), value: 'operator' },
        { text: this.$t('takedown.colTime'), value: 'create_time' },
        { text: this.$t('takedown.colActions'), value: 'actions', sortable: false, align: 'end' },
      ];
    },
  },
  mounted() {
    this.load();
  },
  methods: {
    formatTime(v) {
      if (!v) return '—';
      try { return new Date(v).toLocaleString(); } catch (e) { return v; }
    },
    async load() {
      this.loading = true;
      try {
        const rsp = await this.$backend('/admin/takedown/list');
        if (rsp.err === 'ok') {
          this.items = rsp.items || [];
          this.notice = rsp.notice || '';
          this.defaultNotice = rsp.default_notice || '';
        } else {
          this.$alert('error', rsp.msg || this.$t('takedown.failed'));
        }
      } catch (e) {
        this.$alert('error', (e && e.message) || this.$t('takedown.failed'));
      } finally {
        this.loading = false;
      }
    },
    openAdd() {
      this.form_book_id = '';
      this.form_reason = '';
      this.dialog_add = true;
    },
    async apply(endpoint, payload, successMsg) {
      if (this.submitting) return;
      this.submitting = true;
      try {
        const rsp = await this.$backend('/admin/takedown/' + endpoint, {
          method: 'POST',
          body: JSON.stringify(payload),
        });
        if (rsp.err !== 'ok') {
          this.$alert('error', rsp.msg || this.$t('takedown.failed'));
          return false;
        }
        this.items = rsp.items || [];
        if (rsp.notice) this.notice = rsp.notice;
        this.selected = [];
        this.$alert('success', rsp.msg || successMsg);
        return true;
      } catch (e) {
        this.$alert('error', (e && e.message) || this.$t('takedown.failed'));
        return false;
      } finally {
        this.submitting = false;
      }
    },
    restore(ids) {
      return this.apply('remove', { book_ids: ids }, this.$t('takedown.restored'));
    },
    async submitAdd() {
      const id = parseInt(this.form_book_id, 10);
      if (!id || id <= 0) {
        this.$alert('error', this.$t('takedown.invalidBookId'));
        return;
      }
      const done = await this.apply('set', { book_id: id, reason: this.form_reason || '' }, this.$t('takedown.applied'));
      if (done) this.dialog_add = false;
    },
  },
};
</script>
