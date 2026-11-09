<template>
  <v-container fluid class="pa-4">
    <!-- build.27：作者归一化 + 作者清理合并为一个工具，入口只保留「工具箱 → 作者归一 / 清理」 -->
    <v-row class="mb-3" align="center">
      <v-col class="text-center">
        <span class="text-h5 font-weight-bold">{{ $t('authorTools.title') }}</span>
      </v-col>
      <v-col cols="auto">
        <v-btn small color="error" @click="$router.push('/admin/toolbox')">
          <v-icon small left>mdi-close</v-icon>{{ $t('authorTools.close') }}
        </v-btn>
      </v-col>
    </v-row>

    <v-alert type="info" text dense class="mb-3">
      <div class="text-body-2">{{ $t('authorTools.hint') }}</div>
      <div class="text-caption mt-1">{{ $t('authorTools.hint2') }}</div>
    </v-alert>

    <v-tabs v-model="tab" background-color="transparent" grow class="mb-3">
      <v-tab><v-icon small left>mdi-stethoscope</v-icon>{{ $t('authorTools.tabNorm') }}</v-tab>
      <v-tab><v-icon small left>mdi-broom</v-icon>{{ $t('authorTools.tabClean') }}</v-tab>
    </v-tabs>

    <!-- eager：两个子组件始终挂载，「体检结果 → 一键带入清理」才能立刻拿到 ref -->
    <v-tabs-items v-model="tab">
      <v-tab-item eager>
        <AuthorNorm embedded @open-clean="goClean" />
      </v-tab-item>
      <v-tab-item eager>
        <AuthorClean ref="clean" embedded />
      </v-tab-item>
    </v-tabs-items>
  </v-container>
</template>

<script>
import AuthorNorm from './author_norm.vue';
import AuthorClean from './author_clean.vue';

export default {
  components: { AuthorNorm, AuthorClean },
  data: () => ({
    tab: 0,
  }),
  created() {
    this.$store.commit('navbar', true);
  },
  methods: {
    // 归一化页里点「去清理」：切 Tab 并把脏名预填进清理表单，不再跳到另一个页面
    goClean(name) {
      this.tab = 1;
      if (name) {
        this.$nextTick(() => {
          if (this.$refs.clean) this.$refs.clean.prefill(name);
        });
      }
    },
  },
};
</script>
