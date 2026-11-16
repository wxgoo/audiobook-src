<template>
    <div class="scan-ignore-dirs-editor">
        <div class="d-flex align-center mb-2">
            <v-text-field
                v-model="newName"
                dense
                outlined
                hide-details
                :label="$t('settings.scan_ignore_dirs_add')"
                :placeholder="$t('settings.scan_ignore_dirs_placeholder')"
                :error-messages="newNameError"
                class="mr-2"
                @keyup.enter="addName"
            ></v-text-field>
            <v-btn
                color="primary"
            depressed
            :disabled="!newName || !!newNameError"
            @click="addName"
            >
                <v-icon left>mdi-plus</v-icon>
                {{ $t("settings.scan_ignore_dirs_add") }}
            </v-btn>
        </div>

        <v-alert
            v-if="problems.invalid.length || problems.duplicates.length"
            type="warning"
            dense
            outlined
            class="mb-2"
        >
            <div v-if="problems.invalid.length">
                {{ $t("settings.scan_ignore_dirs_invalid_names", { names: problems.invalid.join(", ") }) }}
            </div>
            <div v-if="problems.duplicates.length">
                {{ $t("settings.scan_ignore_dirs_duplicate", { names: problems.duplicates.join(", ") }) }}
            </div>
        </v-alert>

        <v-textarea
            :value="value.join('\n')"
            outlined
            rows="3"
            auto-grow
            hide-details
            class="scan-ignore-dirs-textarea"
            @input="onTextareaInput"
        ></v-textarea>

        <div class="caption grey--text mt-1">{{ $t("settings.scan_ignore_dirs_hint") }}</div>

        <div v-if="value.length" class="mt-2">
            <v-chip
                v-for="(name, i) in value"
                :key="name + '-' + i"
                class="mr-1 mb-1"
                small
                close
                @click="removeName(i)"
            >
                {{ name }}
            </v-chip>
        </div>
    </div>
</template>

<script>
/**
 * 扫描导入「忽略目录」编辑器。
 *
 * 规则（与服务端 webserver/services/scan_service.py 的归一化同口径）：
 * 按**目录名精确匹配**——不含路径、不支持通配符；命中的目录及其子目录在扫描时跳过。
 * 非法目录名（含 / \ : * ? " < > | 或控制字符，或为 . / ..）与重复名会阻止保存。
 */
const INVALID_CHARS = '/\\:*?"<>|';

export function isInvalidScanIgnoreDirName(name) {
    if (!name) return true;
    const trimmed = String(name).trim();
    if (!trimmed || trimmed === "." || trimmed === "..") return true;
    for (const ch of trimmed) {
        if (INVALID_CHARS.includes(ch)) return true;
        if (ch.charCodeAt(0) < 32) return true;
    }
    return false;
}

export default {
    name: "ScanIgnoreDirsEditor",
    props: {
        value: {
            type: Array,
            default: () => [],
        },
    },
    data() {
        return {
            newName: "",
        };
    },
    computed: {
        problems() {
            const invalid = [];
            const counts = {};
            for (const raw of this.value) {
                const name = (raw || "").trim();
                if (!name) continue;
                if (isInvalidScanIgnoreDirName(name)) {
                    invalid.push(name);
                    continue;
                }
                counts[name] = (counts[name] || 0) + 1;
            }
            const duplicates = Object.keys(counts).filter((k) => counts[k] > 1);
            return { invalid, duplicates };
        },
        newNameError() {
            if (!this.newName) return "";
            if (isInvalidScanIgnoreDirName(this.newName)) {
                return this.$t("settings.scan_ignore_dirs_invalid");
            }
            const trimmed = this.newName.trim();
            if (this.value.some((v) => (v || "").trim() === trimmed)) {
                return this.$t("settings.scan_ignore_dirs_duplicate", { names: trimmed });
            }
            return "";
        },
    },
    methods: {
        emit(list) {
            this.$emit("input", list);
        },
        addName() {
            if (!this.newName || this.newNameError) return;
            const trimmed = this.newName.trim();
            this.emit([...this.value, trimmed]);
            this.newName = "";
        },
        removeName(index) {
            const list = this.value.slice();
            list.splice(index, 1);
            this.emit(list);
        },
        onTextareaInput(e) {
            // 文本域是「一行一个目录名」的直接编辑入口
            const list = String(e.target.value || "")
                .split("\n")
                .map((s) => s.trim())
                .filter(Boolean);
            this.emit(list);
        },
    },
};
</script>

<style scoped>
.scan-ignore-dirs-textarea >>> textarea {
    font-family: monospace;
}
</style>
