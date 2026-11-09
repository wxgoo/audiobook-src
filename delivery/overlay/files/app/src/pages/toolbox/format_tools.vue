<template>
  <v-container fluid class="pa-4">
    <!-- build.27：格式合并 + 格式精简合并为一个工具，入口只保留「工具箱 → 格式合并 / 精简」 -->
    <v-row class="mb-3" align="center">
      <v-col class="text-center">
        <span class="text-h5 font-weight-bold">{{ $t('formatTools.title') }}</span>
      </v-col>
      <v-col cols="auto">
        <v-btn small color="error" @click="$router.push('/admin/toolbox')">
          <v-icon small left>mdi-close</v-icon>{{ $t('formatTools.close') }}
        </v-btn>
      </v-col>
    </v-row>

    <v-alert type="info" text dense class="mb-3">
      <div class="text-body-2">{{ $t('formatTools.hint') }}</div>
      <div class="text-caption mt-1">{{ $t('formatTools.hint2') }}</div>
    </v-alert>

    <v-tabs v-model="tab" background-color="transparent" grow class="mb-3">
      <v-tab><v-icon small left>mdi-call-merge</v-icon>{{ $t('formatTools.tabMerge') }}</v-tab>
      <v-tab><v-icon small left>mdi-content-cut</v-icon>{{ $t('formatTools.tabPrune') }}</v-tab>
    </v-tabs>

    <v-tabs-items v-model="tab">
      <v-tab-item eager>
        <MergeFormats embedded />
      </v-tab-item>
      <v-tab-item eager>
        <FormatsPruning embedded />
      </v-tab-item>
    </v-tabs-items>
  </v-container>
</template>

<script>
import MergeFormats from './merge_formats_tool.vue';
import FormatsPruning from './formats_pruning.vue';

export default {
  components: { MergeFormats, FormatsPruning },
  data: () => ({
    tab: 0,
  }),
  created() {
    this.$store.commit('navbar', true);
  },
};
</script>
