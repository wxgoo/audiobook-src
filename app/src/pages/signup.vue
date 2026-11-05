<template>
    <v-row justify=center class="fill-center">
      <v-col xs=12 sm=8 md=4>
        <v-card class="elevation-12">
            <v-toolbar dark color="primary">
                <v-toolbar-title>{{ $t('signup.title') }}</v-toolbar-title>
            </v-toolbar>
            <v-card-text>
                <v-form ref="form" @submit.prevent="signup">
                    <v-text-field required prepend-icon="mdi-account" v-model="username"  :label="$t('signup.username')"   type="text"     autocomplete="new-username"  :rules="[rules.user]"         ></v-text-field>
                    <v-text-field required prepend-icon="mdi-lock"   v-model="password"  :label="$t('signup.password')"   type="password" autocomplete="new-password"  :rules="rulesPass" :hint="$t('signup.passwordHint')" persistent-hint ></v-text-field>
                    <v-text-field required prepend-icon="mdi-lock"   v-model="password2" :label="$t('signup.confirmPassword')" type="password" autocomplete="new-password2" :rules="[valid]"                  ></v-text-field>
                    <v-text-field required prepend-icon="mdi-account-outline"   v-model="nickname"  :label="$t('signup.nickname')"   type="text"     autocomplete="new-nickname"  :rules="[rules.nick]"         ></v-text-field>
                    <v-text-field required prepend-icon="mdi-email"  v-model="email"     :label="$t('signup.email')"      type="text"     autocomplete="new-email"     :rules="[rules.email]"            ></v-text-field>
                    <!-- §出生年份必填（r11）§ 管理员审核时要按年龄分组限额（有些书
                         不适合某个年龄段），所以注册即收集，并明确提示不得虚报。
                         存出生年份而不是「当前几岁」：年龄年年变，存死了就会
                         「12 岁注册、三年后还是 12 岁」，该解锁的书永远解锁不了。 -->
                    <v-text-field required prepend-icon="mdi-cake-variant" v-model="birthYear" :label="$t('signup.birthYear')"
                                  type="number" :min="birthYearMin" :max="birthYearMax" :rules="rulesBirthYear"
                                  :hint="$t('signup.birthYearHint')" persistent-hint ></v-text-field>
                    <div v-if="agePreview > 0" class="text-caption grey--text mt-1 mb-2">
                        {{ $t('signup.birthYearPreview', { age: agePreview, year: birthYearMax }) }}
                    </div>
                    <v-checkbox v-model="ageHonest" :label="$t('signup.ageHonest')" :rules="[v => !!v || $t('signup.ageHonestRequired')]" class="mt-4" ></v-checkbox>
                </v-form>
                <div align="center">
                    <v-btn dark large rounded color="red" @click="signup">{{ $t('signup.registerButton') }}</v-btn>
                </div>
            </v-card-text>

            <v-alert v-if="failmsg" type="error">{{ failmsg }}</v-alert>
        </v-card>
      </v-col>
    </v-row>
</template>

<script>
import {
    passwordRules,
    birthYearRules,
    checkPassword,
    checkBirthYear,
    ageFromBirthYear,
    BIRTH_YEAR_MIN,
    currentYear,
} from '~/utils/accountRules';

export default {
    created() {
        this.$store.commit("navbar", false);
    },
    data: () => ({
        username: "",
        password: "",
        password2: "",
        nickname: "",
        email: "",
        birthYear: "",
        ageHonest: false,
        failmsg: "",
        validmsg: "",
        rules: {
            user: v => ( 20 >= v.length && v.length >= 3) || '3 ~ 20 字符',
            nick: v => v.length >= 2 || '最少2个字符',
            email: function (email) {
                var re = /^(([^<>()[\]\\.,;:\s@"]+(\.[^<>()[\]\\.,;:\s@"]+)*)|(".+"))@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\])|(([a-zA-Z\-0-9]+\.)+[a-zA-Z]{2,}))$/;
                return re.test(email) || "错误的邮箱格式";
            },
        },

    }),
    head() {
        return {
            title: this.$t('signup.pageTitle'),
        };
    },
    computed: {
        // 密码与年龄规则要用到 i18n，放 computed 里才能跟随语言切换
        rulesPass() {
            return passwordRules((k) => this.$t(k));
        },
        rulesBirthYear() {
            return birthYearRules((k) => this.$t(k));
        },
        birthYearMin() {
            return BIRTH_YEAR_MIN;
        },
        birthYearMax() {
            return currentYear();
        },
        // 让用户当场看到「你今年几岁」，填错年份能立刻发现
        agePreview() {
            return ageFromBirthYear(this.birthYear);
        },
    },
    methods: {
        valid: function(v) {
            if ( v.length < 6 ) {
                return this.$t('signup.pwdTooShort');
            }
            return v == this.password || "密码不匹配";
        },
        signup: function() {
            if ( ! this.$refs.form.validate() ) {
                return false;
            }
            // 后端还会再校验一次，这里先挡一道，省一次往返
            const pwdErr = checkPassword(this.password, (k) => this.$t(k));
            if (pwdErr) {
                this.failmsg = pwdErr;
                return false;
            }
            const yearErr = checkBirthYear(this.birthYear, (k) => this.$t(k));
            if (yearErr) {
                this.failmsg = yearErr;
                return false;
            }
            if (!this.ageHonest) {
                this.failmsg = this.$t('signup.ageHonestRequired');
                return false;
            }

            var data = new URLSearchParams();
            data.append('username', this.username);
            data.append('password', this.password);
            data.append('nickname', this.nickname);
            data.append('email', this.email);
            data.append('birth_year', String(this.birthYear));
            this.$backend('/user/sign_up', {
                method: 'POST',
                body: data,
            })
            .then( rsp => {
                if ( rsp.err != 'ok' ) {
                    this.failmsg = rsp.msg;
                } else {
                    this.$store.commit("navbar", true);
                    this.$router.push("/");
                }
            });
        }
    },
}
</script>

<style>
.fill-center {
    margin-top: 6%;
}
</style>
