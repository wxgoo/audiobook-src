<template>
    <v-row>
        <template v-if="meta == 'rating'">
            <v-col cols=4 sm=2 v-for="item in meta_items" :key="item.name" >
                <v-chip :to="item.href" color="primary" >
                    {{ item.name }}{{ $t('listMeta.ratingSuffix') }}
                    <span v-if="item.count">&nbsp;({{ item.count }})</span>
                </v-chip>
            </v-col>
        </template >
        <v-col v-else>
            <v-chip class="ma-1" v-for="item in meta_items" :to="item.href" :key="item.name" color="primary" >
                {{ item.name }}
                <span v-if="item.count">&nbsp;({{ item.count }})</span>
            </v-chip>
            <v-btn v-if="total > items.length" @click="expand()" color="primary" rounded>{{ $t('listMeta.showAll') }}</v-btn>
        </v-col>
    </v-row>
</template>

<script>
export default {
    computed: {
        page_cnt: function() {
            return Math.max(1, Math.ceil(this.total / this.page_size));
        },
        meta_items: function() {
            var prefix = this.$route.path + "/";
            return this.items.map(d => {
                d.href = prefix + encodeURIComponent(d.name);
                return d;
            });
        },
    },
    data: () => ({
        meta: "",
        page: 0,
        items: [],
        total: 0,
        show_all: false,
        page_size: 20,
        ssr_loaded: false,
    }),
    async asyncData({ app, route, res }) {
        if (res !== undefined) {
            res.setHeader('Cache-Control', 'no-cache');
        }
        const rsp = await app.$backend(route.fullPath);
        // 与 ListBook 一致：只有服务端真取到数据才标记，静态产物里构建期
        // asyncData 的结果不能当成「运行时已加载」。
        if (rsp && rsp.err === 'ok') {
            return Object.assign({}, rsp, { ssr_loaded: true });
        }
        return rsp || {};
    },
    head() {
        var path = this.$route.path;
        var titles = {
            tag: this.$t('listMeta.allTags'),
            series: this.$t('listMeta.allSeries'),
            rating: this.$t('listMeta.allRatings'),
            author: this.$t('listMeta.allAuthors'),
            publisher: this.$t('listMeta.allPublishers'),
            language: this.$t('listMeta.allLanguages'),
        };
        // 从路径中获取meta类型
        var meta = path.split("/")[1];
        if (titles[meta] !== undefined) {
            return {
                title: titles[meta],
            };
        }
        return {};
    },
    created() {
        //this.init(this.$route);
    },
    mounted() {
        // 强刷/直接进入这些列表路由时，静态产物不会重跑 asyncData，必须补一次取数；
        // 服务端已取到数据（ssr_loaded）则不重复请求。
        if (!this.ssr_loaded) {
            this.init(this.$route);
        }
    },
    beforeRouteEnter(to, from, next) {
        next();
    },
    beforeRouteUpdate(to, from, next) {
        this.init(to, next);
    },
    methods: {
        init(route, next) {
            this.$store.commit('navbar', true);
            this.meta = this.$route.path.split("/")[1];
            this.$backend("/"+this.meta + (this.show_all?"?show=all":"") )
            .then(rsp => {
                this.items = rsp.items;
                this.total = rsp.total;
            })
            if ( next ) next()
        },
        expand() {
            this.show_all = !this.show_all;
            this.init(this.$route);
        },
    },
}
</script>