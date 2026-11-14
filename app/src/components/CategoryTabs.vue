<template>
  <!-- 分类 tab 横向条：/categories（分类浏览）与 /audiobooks（有声书）共用。
       迁移自 categories.vue 的模板与样式（原两处各写一份，改一处忘另一处）。 -->
  <div class="folder-tabs-wrapper">
    <div class="folder-tabs">
      <div
        v-for="(category, index) in categories"
        :key="category.name + '-' + index"
        :class="['folder-tab', { 'active': value === index }]"
        @click="$emit('input', index)"
      >
        <v-icon small class="tab-icon" :color="tabIconColor(category, index)">{{ category.icon || 'mdi-tag-outline' }}</v-icon>
        <span class="tab-name">{{ category.label || category.name }}</span>
        <span class="tab-count">({{ category.count }})</span>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: "CategoryTabs",
  props: {
    // [{name, count, icon?, color?, label?}]，label 缺省显示 name（「全部」tab 用 label）
    categories: { type: Array, default: () => [] },
    // 当前选中索引（v-model 兼容 Vue 2）
    value: { type: Number, default: 0 },
  },
  methods: {
    // 分类图标由后端按名称规则给出（见 webserver/base/category_icons.py）；
    // 选中态是深蓝底，图标改用白色，未选中用分类自己的颜色。
    tabIconColor(category, index) {
      if (this.value === index) return "white";
      return (category && category.color) || "";
    },
  },
};
</script>

<style scoped>
.folder-tabs-wrapper {
  padding: 16px;
}

.folder-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.folder-tab {
  display: inline-flex;
  align-items: center;
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.3s ease;
  user-select: none;
  position: relative;
  overflow: hidden;
}

.folder-tab::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  background: transparent;
  border-radius: 2px;
  transition: all 0.3s ease;
}

.folder-tab .tab-icon {
  margin-right: 6px;
}

.folder-tab .tab-name {
  font-weight: 500;
  font-size: 14px;
}

.folder-tab .tab-count {
  margin-left: 4px;
  font-size: 12px;
  opacity: 0.7;
}

.folder-tab:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.folder-tab.active {
  transform: translateY(-4px);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.2);
}

.folder-tab.active::before {
  background: currentColor;
}

.folder-tab.active .tab-count {
  opacity: 1;
  font-weight: 600;
}

.folder-tab.active .tab-name {
  font-weight: 600;
}

.theme--light .folder-tab {
  background-color: #f5f5f5;
  color: #424242;
  border: 1px solid #e0e0e0;
}

.theme--light .folder-tab:hover {
  background-color: #eeeeee;
}

.theme--light .folder-tab.active {
  background-color: #1976d2;
  color: white;
  border-color: #1976d2;
}

.theme--dark .folder-tab {
  background-color: #2d2d2d;
  color: #e0e0e0;
  border: 1px solid #424242;
}

.theme--dark .folder-tab:hover {
  background-color: #3d3d3d;
}

.theme--dark .folder-tab.active {
  background-color: #1976d2;
  color: white;
  border-color: #1976d2;
}

@media (max-width: 600px) {
  .folder-tabs {
    gap: 6px;
  }

  .folder-tab {
    padding: 6px 12px;
    font-size: 13px;
  }

  .folder-tab .tab-name {
    font-size: 13px;
  }

  .folder-tab .tab-icon {
    margin-right: 4px;
  }

  .folder-tab .tab-count {
    font-size: 11px;
  }
}
</style>
