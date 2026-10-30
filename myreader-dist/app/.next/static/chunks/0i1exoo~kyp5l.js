(globalThis.TURBOPACK||(globalThis.TURBOPACK=[])).push(["object"==typeof document?document.currentScript:void 0,274070,431270,727476,162755,t=>{"use strict";var e,a,n,i=t.i(11173);function r(t){return(r="function"==typeof Symbol&&"symbol"==typeof Symbol.iterator?function(t){return typeof t}:function(t){return t&&"function"==typeof Symbol&&t.constructor===Symbol&&t!==Symbol.prototype?"symbol":typeof t})(t)}var o=/^\s+/,l=/\s+$/;function c(t,e){if(e=e||{},(t=t||"")instanceof c)return t;if(!(this instanceof c))return new c(t,e);var a,n,i,h,s,d,g,f,u,p,m,v,b,w,M,y,z,x,k,$,A=(n={r:0,g:0,b:0},i=1,h=null,s=null,d=null,g=!1,f=!1,"string"==typeof(a=t)&&(a=function(t){t=t.replace(o,"").replace(l,"").toLowerCase();var e,a=!1;if(H[t])t=H[t],a=!0;else if("transparent"==t)return{r:0,g:0,b:0,a:0,format:"name"};return(e=B.rgb.exec(t))?{r:e[1],g:e[2],b:e[3]}:(e=B.rgba.exec(t))?{r:e[1],g:e[2],b:e[3],a:e[4]}:(e=B.hsl.exec(t))?{h:e[1],s:e[2],l:e[3]}:(e=B.hsla.exec(t))?{h:e[1],s:e[2],l:e[3],a:e[4]}:(e=B.hsv.exec(t))?{h:e[1],s:e[2],v:e[3]}:(e=B.hsva.exec(t))?{h:e[1],s:e[2],v:e[3],a:e[4]}:(e=B.hex8.exec(t))?{r:L(e[1]),g:L(e[2]),b:L(e[3]),a:L(e[4])/255,format:a?"name":"hex8"}:(e=B.hex6.exec(t))?{r:L(e[1]),g:L(e[2]),b:L(e[3]),format:a?"name":"hex"}:(e=B.hex4.exec(t))?{r:L(e[1]+""+e[1]),g:L(e[2]+""+e[2]),b:L(e[3]+""+e[3]),a:L(e[4]+""+e[4])/255,format:a?"name":"hex8"}:!!(e=B.hex3.exec(t))&&{r:L(e[1]+""+e[1]),g:L(e[2]+""+e[2]),b:L(e[3]+""+e[3]),format:a?"name":"hex"}}(a)),"object"==r(a)&&(G(a.r)&&G(a.g)&&G(a.b)?(u=a.r,p=a.g,m=a.b,n={r:255*I(u,255),g:255*I(p,255),b:255*I(m,255)},g=!0,f="%"===String(a.r).substr(-1)?"prgb":"rgb"):G(a.h)&&G(a.s)&&G(a.v)?(h=C(a.s),s=C(a.v),v=a.h,b=h,w=s,v=6*I(v,360),b=I(b,100),w=I(w,100),M=Math.floor(v),y=v-M,z=w*(1-b),x=w*(1-y*b),k=w*(1-(1-y)*b),n={r:255*[w,x,z,z,k,w][$=M%6],g:255*[k,w,w,x,z,z][$],b:255*[z,z,k,w,w,x][$]},g=!0,f="hsv"):G(a.h)&&G(a.s)&&G(a.l)&&(h=C(a.s),d=C(a.l),n=function(t,e,a){var n,i,r;function o(t,e,a){return(a<0&&(a+=1),a>1&&(a-=1),a<1/6)?t+(e-t)*6*a:a<.5?e:a<2/3?t+(e-t)*(2/3-a)*6:t}if(t=I(t,360),e=I(e,100),a=I(a,100),0===e)n=i=r=a;else{var l=a<.5?a*(1+e):a+e-a*e,c=2*a-l;n=o(c,l,t+1/3),i=o(c,l,t),r=o(c,l,t-1/3)}return{r:255*n,g:255*i,b:255*r}}(a.h,h,d),g=!0,f="hsl"),a.hasOwnProperty("a")&&(i=a.a)),i=S(i),{ok:g,format:a.format||f,r:Math.min(255,Math.max(n.r,0)),g:Math.min(255,Math.max(n.g,0)),b:Math.min(255,Math.max(n.b,0)),a:i});this._originalInput=t,this._r=A.r,this._g=A.g,this._b=A.b,this._a=A.a,this._roundA=Math.round(100*this._a)/100,this._format=e.format||A.format,this._gradientType=e.gradientType,this._r<1&&(this._r=Math.round(this._r)),this._g<1&&(this._g=Math.round(this._g)),this._b<1&&(this._b=Math.round(this._b)),this._ok=A.ok}function h(t,e,a){t=I(t,255);var n,i,r=Math.max(t,e=I(e,255),a=I(a,255)),o=Math.min(t,e,a),l=(r+o)/2;if(r==o)n=i=0;else{var c=r-o;switch(i=l>.5?c/(2-r-o):c/(r+o),r){case t:n=(e-a)/c+6*(e<a);break;case e:n=(a-t)/c+2;break;case a:n=(t-e)/c+4}n/=6}return{h:n,s:i,l:l}}function s(t,e,a){t=I(t,255);var n,i=Math.max(t,e=I(e,255),a=I(a,255)),r=Math.min(t,e,a),o=i-r;if(i==r)n=0;else{switch(i){case t:n=(e-a)/o+6*(e<a);break;case e:n=(a-t)/o+2;break;case a:n=(t-e)/o+4}n/=6}return{h:n,s:0===i?0:o/i,v:i}}function d(t,e,a,n){var i=[_(Math.round(t).toString(16)),_(Math.round(e).toString(16)),_(Math.round(a).toString(16))];return n&&i[0].charAt(0)==i[0].charAt(1)&&i[1].charAt(0)==i[1].charAt(1)&&i[2].charAt(0)==i[2].charAt(1)?i[0].charAt(0)+i[1].charAt(0)+i[2].charAt(0):i.join("")}function g(t,e,a,n){return[_(V(n)),_(Math.round(t).toString(16)),_(Math.round(e).toString(16)),_(Math.round(a).toString(16))].join("")}function f(t,e){e=0===e?0:e||10;var a=c(t).toHsl();return a.s-=e/100,a.s=A(a.s),c(a)}function u(t,e){e=0===e?0:e||10;var a=c(t).toHsl();return a.s+=e/100,a.s=A(a.s),c(a)}function p(t){return c(t).desaturate(100)}function m(t,e){e=0===e?0:e||10;var a=c(t).toHsl();return a.l+=e/100,a.l=A(a.l),c(a)}function v(t,e){e=0===e?0:e||10;var a=c(t).toRgb();return a.r=Math.max(0,Math.min(255,a.r-Math.round(-(e/100*255)))),a.g=Math.max(0,Math.min(255,a.g-Math.round(-(e/100*255)))),a.b=Math.max(0,Math.min(255,a.b-Math.round(-(e/100*255)))),c(a)}function b(t,e){e=0===e?0:e||10;var a=c(t).toHsl();return a.l-=e/100,a.l=A(a.l),c(a)}function w(t,e){var a=c(t).toHsl(),n=(a.h+e)%360;return a.h=n<0?360+n:n,c(a)}function M(t){var e=c(t).toHsl();return e.h=(e.h+180)%360,c(e)}function y(t,e){if(isNaN(e)||e<=0)throw Error("Argument to polyad must be a positive number");for(var a=c(t).toHsl(),n=[c(t)],i=360/e,r=1;r<e;r++)n.push(c({h:(a.h+r*i)%360,s:a.s,l:a.l}));return n}function z(t){var e=c(t).toHsl(),a=e.h;return[c(t),c({h:(a+72)%360,s:e.s,l:e.l}),c({h:(a+216)%360,s:e.s,l:e.l})]}function x(t,e,a){e=e||6,a=a||30;var n=c(t).toHsl(),i=360/a,r=[c(t)];for(n.h=(n.h-(i*e>>1)+720)%360;--e;)n.h=(n.h+i)%360,r.push(c(n));return r}function k(t,e){e=e||6;for(var a=c(t).toHsv(),n=a.h,i=a.s,r=a.v,o=[],l=1/e;e--;)o.push(c({h:n,s:i,v:r})),r=(r+l)%1;return o}c.prototype={isDark:function(){return 128>this.getBrightness()},isLight:function(){return!this.isDark()},isValid:function(){return this._ok},getOriginalInput:function(){return this._originalInput},getFormat:function(){return this._format},getAlpha:function(){return this._a},getBrightness:function(){var t=this.toRgb();return(299*t.r+587*t.g+114*t.b)/1e3},getLuminance:function(){var t,e,a,n=this.toRgb();return t=n.r/255,e=n.g/255,.2126*(t<=.03928?t/12.92:Math.pow((t+.055)/1.055,2.4))+.7152*(e<=.03928?e/12.92:Math.pow((e+.055)/1.055,2.4))+.0722*((a=n.b/255)<=.03928?a/12.92:Math.pow((a+.055)/1.055,2.4))},setAlpha:function(t){return this._a=S(t),this._roundA=Math.round(100*this._a)/100,this},toHsv:function(){var t=s(this._r,this._g,this._b);return{h:360*t.h,s:t.s,v:t.v,a:this._a}},toHsvString:function(){var t=s(this._r,this._g,this._b),e=Math.round(360*t.h),a=Math.round(100*t.s),n=Math.round(100*t.v);return 1==this._a?"hsv("+e+", "+a+"%, "+n+"%)":"hsva("+e+", "+a+"%, "+n+"%, "+this._roundA+")"},toHsl:function(){var t=h(this._r,this._g,this._b);return{h:360*t.h,s:t.s,l:t.l,a:this._a}},toHslString:function(){var t=h(this._r,this._g,this._b),e=Math.round(360*t.h),a=Math.round(100*t.s),n=Math.round(100*t.l);return 1==this._a?"hsl("+e+", "+a+"%, "+n+"%)":"hsla("+e+", "+a+"%, "+n+"%, "+this._roundA+")"},toHex:function(t){return d(this._r,this._g,this._b,t)},toHexString:function(t){return"#"+this.toHex(t)},toHex8:function(t){var e,a,n,i,r,o;return e=this._r,a=this._g,n=this._b,i=this._a,r=t,o=[_(Math.round(e).toString(16)),_(Math.round(a).toString(16)),_(Math.round(n).toString(16)),_(V(i))],r&&o[0].charAt(0)==o[0].charAt(1)&&o[1].charAt(0)==o[1].charAt(1)&&o[2].charAt(0)==o[2].charAt(1)&&o[3].charAt(0)==o[3].charAt(1)?o[0].charAt(0)+o[1].charAt(0)+o[2].charAt(0)+o[3].charAt(0):o.join("")},toHex8String:function(t){return"#"+this.toHex8(t)},toRgb:function(){return{r:Math.round(this._r),g:Math.round(this._g),b:Math.round(this._b),a:this._a}},toRgbString:function(){return 1==this._a?"rgb("+Math.round(this._r)+", "+Math.round(this._g)+", "+Math.round(this._b)+")":"rgba("+Math.round(this._r)+", "+Math.round(this._g)+", "+Math.round(this._b)+", "+this._roundA+")"},toPercentageRgb:function(){return{r:Math.round(100*I(this._r,255))+"%",g:Math.round(100*I(this._g,255))+"%",b:Math.round(100*I(this._b,255))+"%",a:this._a}},toPercentageRgbString:function(){return 1==this._a?"rgb("+Math.round(100*I(this._r,255))+"%, "+Math.round(100*I(this._g,255))+"%, "+Math.round(100*I(this._b,255))+"%)":"rgba("+Math.round(100*I(this._r,255))+"%, "+Math.round(100*I(this._g,255))+"%, "+Math.round(100*I(this._b,255))+"%, "+this._roundA+")"},toName:function(){return 0===this._a?"transparent":!(this._a<1)&&($[d(this._r,this._g,this._b,!0)]||!1)},toFilter:function(t){var e="#"+g(this._r,this._g,this._b,this._a),a=e,n=this._gradientType?"GradientType = 1, ":"";if(t){var i=c(t);a="#"+g(i._r,i._g,i._b,i._a)}return"progid:DXImageTransform.Microsoft.gradient("+n+"startColorstr="+e+",endColorstr="+a+")"},toString:function(t){var e=!!t;t=t||this._format;var a=!1,n=this._a<1&&this._a>=0;return!e&&n&&("hex"===t||"hex6"===t||"hex3"===t||"hex4"===t||"hex8"===t||"name"===t)?"name"===t&&0===this._a?this.toName():this.toRgbString():("rgb"===t&&(a=this.toRgbString()),"prgb"===t&&(a=this.toPercentageRgbString()),("hex"===t||"hex6"===t)&&(a=this.toHexString()),"hex3"===t&&(a=this.toHexString(!0)),"hex4"===t&&(a=this.toHex8String(!0)),"hex8"===t&&(a=this.toHex8String()),"name"===t&&(a=this.toName()),"hsl"===t&&(a=this.toHslString()),"hsv"===t&&(a=this.toHsvString()),a||this.toHexString())},clone:function(){return c(this.toString())},_applyModification:function(t,e){var a=t.apply(null,[this].concat([].slice.call(e)));return this._r=a._r,this._g=a._g,this._b=a._b,this.setAlpha(a._a),this},lighten:function(){return this._applyModification(m,arguments)},brighten:function(){return this._applyModification(v,arguments)},darken:function(){return this._applyModification(b,arguments)},desaturate:function(){return this._applyModification(f,arguments)},saturate:function(){return this._applyModification(u,arguments)},greyscale:function(){return this._applyModification(p,arguments)},spin:function(){return this._applyModification(w,arguments)},_applyCombination:function(t,e){return t.apply(null,[this].concat([].slice.call(e)))},analogous:function(){return this._applyCombination(x,arguments)},complement:function(){return this._applyCombination(M,arguments)},monochromatic:function(){return this._applyCombination(k,arguments)},splitcomplement:function(){return this._applyCombination(z,arguments)},triad:function(){return this._applyCombination(y,[3])},tetrad:function(){return this._applyCombination(y,[4])}},c.fromRatio=function(t,e){if("object"==r(t)){var a={};for(var n in t)t.hasOwnProperty(n)&&("a"===n?a[n]=t[n]:a[n]=C(t[n]));t=a}return c(t,e)},c.equals=function(t,e){return!!t&&!!e&&c(t).toRgbString()==c(e).toRgbString()},c.random=function(){return c.fromRatio({r:Math.random(),g:Math.random(),b:Math.random()})},c.mix=function(t,e,a){a=0===a?0:a||50;var n=c(t).toRgb(),i=c(e).toRgb(),r=a/100;return c({r:(i.r-n.r)*r+n.r,g:(i.g-n.g)*r+n.g,b:(i.b-n.b)*r+n.b,a:(i.a-n.a)*r+n.a})},c.readability=function(t,e){var a=c(t),n=c(e);return(Math.max(a.getLuminance(),n.getLuminance())+.05)/(Math.min(a.getLuminance(),n.getLuminance())+.05)},c.isReadable=function(t,e,a){var n,i,r,o,l,h=c.readability(t,e);switch(l=!1,(i=((n=(n=a)||{level:"AA",size:"small"}).level||"AA").toUpperCase(),r=(n.size||"small").toLowerCase(),"AA"!==i&&"AAA"!==i&&(i="AA"),"small"!==r&&"large"!==r&&(r="small"),o={level:i,size:r}).level+o.size){case"AAsmall":case"AAAlarge":l=h>=4.5;break;case"AAlarge":l=h>=3;break;case"AAAsmall":l=h>=7}return l},c.mostReadable=function(t,e,a){var n,i,r,o,l=null,h=0;i=(a=a||{}).includeFallbackColors,r=a.level,o=a.size;for(var s=0;s<e.length;s++)(n=c.readability(t,e[s]))>h&&(h=n,l=c(e[s]));return c.isReadable(t,l,{level:r,size:o})||!i?l:(a.includeFallbackColors=!1,c.mostReadable(t,["#fff","#000"],a))};var H=c.names={aliceblue:"f0f8ff",antiquewhite:"faebd7",aqua:"0ff",aquamarine:"7fffd4",azure:"f0ffff",beige:"f5f5dc",bisque:"ffe4c4",black:"000",blanchedalmond:"ffebcd",blue:"00f",blueviolet:"8a2be2",brown:"a52a2a",burlywood:"deb887",burntsienna:"ea7e5d",cadetblue:"5f9ea0",chartreuse:"7fff00",chocolate:"d2691e",coral:"ff7f50",cornflowerblue:"6495ed",cornsilk:"fff8dc",crimson:"dc143c",cyan:"0ff",darkblue:"00008b",darkcyan:"008b8b",darkgoldenrod:"b8860b",darkgray:"a9a9a9",darkgreen:"006400",darkgrey:"a9a9a9",darkkhaki:"bdb76b",darkmagenta:"8b008b",darkolivegreen:"556b2f",darkorange:"ff8c00",darkorchid:"9932cc",darkred:"8b0000",darksalmon:"e9967a",darkseagreen:"8fbc8f",darkslateblue:"483d8b",darkslategray:"2f4f4f",darkslategrey:"2f4f4f",darkturquoise:"00ced1",darkviolet:"9400d3",deeppink:"ff1493",deepskyblue:"00bfff",dimgray:"696969",dimgrey:"696969",dodgerblue:"1e90ff",firebrick:"b22222",floralwhite:"fffaf0",forestgreen:"228b22",fuchsia:"f0f",gainsboro:"dcdcdc",ghostwhite:"f8f8ff",gold:"ffd700",goldenrod:"daa520",gray:"808080",green:"008000",greenyellow:"adff2f",grey:"808080",honeydew:"f0fff0",hotpink:"ff69b4",indianred:"cd5c5c",indigo:"4b0082",ivory:"fffff0",khaki:"f0e68c",lavender:"e6e6fa",lavenderblush:"fff0f5",lawngreen:"7cfc00",lemonchiffon:"fffacd",lightblue:"add8e6",lightcoral:"f08080",lightcyan:"e0ffff",lightgoldenrodyellow:"fafad2",lightgray:"d3d3d3",lightgreen:"90ee90",lightgrey:"d3d3d3",lightpink:"ffb6c1",lightsalmon:"ffa07a",lightseagreen:"20b2aa",lightskyblue:"87cefa",lightslategray:"789",lightslategrey:"789",lightsteelblue:"b0c4de",lightyellow:"ffffe0",lime:"0f0",limegreen:"32cd32",linen:"faf0e6",magenta:"f0f",maroon:"800000",mediumaquamarine:"66cdaa",mediumblue:"0000cd",mediumorchid:"ba55d3",mediumpurple:"9370db",mediumseagreen:"3cb371",mediumslateblue:"7b68ee",mediumspringgreen:"00fa9a",mediumturquoise:"48d1cc",mediumvioletred:"c71585",midnightblue:"191970",mintcream:"f5fffa",mistyrose:"ffe4e1",moccasin:"ffe4b5",navajowhite:"ffdead",navy:"000080",oldlace:"fdf5e6",olive:"808000",olivedrab:"6b8e23",orange:"ffa500",orangered:"ff4500",orchid:"da70d6",palegoldenrod:"eee8aa",palegreen:"98fb98",paleturquoise:"afeeee",palevioletred:"db7093",papayawhip:"ffefd5",peachpuff:"ffdab9",peru:"cd853f",pink:"ffc0cb",plum:"dda0dd",powderblue:"b0e0e6",purple:"800080",rebeccapurple:"663399",red:"f00",rosybrown:"bc8f8f",royalblue:"4169e1",saddlebrown:"8b4513",salmon:"fa8072",sandybrown:"f4a460",seagreen:"2e8b57",seashell:"fff5ee",sienna:"a0522d",silver:"c0c0c0",skyblue:"87ceeb",slateblue:"6a5acd",slategray:"708090",slategrey:"708090",snow:"fffafa",springgreen:"00ff7f",steelblue:"4682b4",tan:"d2b48c",teal:"008080",thistle:"d8bfd8",tomato:"ff6347",turquoise:"40e0d0",violet:"ee82ee",wheat:"f5deb3",white:"fff",whitesmoke:"f5f5f5",yellow:"ff0",yellowgreen:"9acd32"},$=c.hexNames=function(t){var e={};for(var a in t)t.hasOwnProperty(a)&&(e[t[a]]=a);return e}(H);function S(t){return(isNaN(t=parseFloat(t))||t<0||t>1)&&(t=1),t}function I(t,e){"string"==typeof(a=t)&&-1!=a.indexOf(".")&&1===parseFloat(a)&&(t="100%");var a,n,i="string"==typeof(n=t)&&-1!=n.indexOf("%");return(t=Math.min(e,Math.max(0,parseFloat(t))),i&&(t=parseInt(t*e,10)/100),1e-6>Math.abs(t-e))?1:t%e/parseFloat(e)}function A(t){return Math.min(1,Math.max(0,t))}function L(t){return parseInt(t,16)}function _(t){return 1==t.length?"0"+t:""+t}function C(t){return t<=1&&(t=100*t+"%"),t}function V(t){return Math.round(255*parseFloat(t)).toString(16)}var B=(a="[\\s|\\(]+("+(e="(?:[-\\+]?\\d*\\.\\d+%?)|(?:[-\\+]?\\d+%?)")+")[,|\\s]+("+e+")[,|\\s]+("+e+")\\s*\\)?",n="[\\s|\\(]+("+e+")[,|\\s]+("+e+")[,|\\s]+("+e+")[,|\\s]+("+e+")\\s*\\)?",{CSS_UNIT:new RegExp(e),rgb:RegExp("rgb"+a),rgba:RegExp("rgba"+n),hsl:RegExp("hsl"+a),hsla:RegExp("hsla"+n),hsv:RegExp("hsv"+a),hsva:RegExp("hsva"+n),hex3:/^#?([0-9a-fA-F]{1})([0-9a-fA-F]{1})([0-9a-fA-F]{1})$/,hex6:/^#?([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})$/,hex4:/^#?([0-9a-fA-F]{1})([0-9a-fA-F]{1})([0-9a-fA-F]{1})([0-9a-fA-F]{1})$/,hex8:/^#?([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})$/});function G(t){return!!B.CSS_UNIT.exec(t)}function E(t){return t<=.04045?t/12.92:Math.pow((t+.055)/1.055,2.4)}function F(t){let{r:e,g:a,b:n}=c(t).toRgb(),i=E(e/255),r=E(a/255),o=E(n/255),l=Math.cbrt(.4122214708*i+.5363325363*r+.0514459929*o),h=Math.cbrt(.2119034982*i+.6806995451*r+.1073969566*o),s=Math.cbrt(.0883024619*i+.2817188376*r+.6299787005*o),d=1.9779984951*l-2.428592205*h+.4505937099*s,g=.0259040371*l+.7827717662*h-.808675766*s,f=Math.sqrt(d*d+g*g),u=180/Math.PI*Math.atan2(g,d);u<0&&(u+=360);let p=(100*(.2104542553*l+.793617785*h-.0040720468*s)).toFixed(4),m=Number(f.toFixed(6)),v=Number(u.toFixed(3));return 0===m?`${p}% 0 0deg`:`${p}% ${m} ${v}deg`}let O=t=>c(t).isDark()?"100% 0 0deg":"0% 0 0deg",T=t=>c(t).isDark()?"#FFFFFF":"#000000",R=t=>{let{bg:e,fg:a,primary:n}=t;return{"base-100":e,"base-200":c(e).darken(5).toHexString(),"base-300":c(e).darken(12).toHexString(),"base-content":a,neutral:c(e).darken(15).desaturate(20).toHexString(),"neutral-content":c(a).lighten(20).desaturate(20).toHexString(),primary:n,secondary:c(n).lighten(20).toHexString(),accent:c(n).analogous()[1].toHexString()}},N=t=>{let{bg:e,fg:a,primary:n}=t;return{"base-100":e,"base-200":c(e).lighten(5).toHexString(),"base-300":c(e).lighten(12).toHexString(),"base-content":a,neutral:c(e).lighten(15).desaturate(20).toHexString(),"neutral-content":c(a).darken(20).desaturate(20).toHexString(),primary:n,secondary:c(n).darken(20).toHexString(),accent:c(n).triad()[1].toHexString()}},P=[{name:"default",label:"Default",colors:{light:R({fg:"#171717",bg:"#ffffff",primary:"#0066cc"}),dark:N({fg:"#e0e0e0",bg:"#222222",primary:"#77bbee"})}},{name:"gray",label:"Gray",colors:{light:R({fg:"#222222",bg:"#e0e0e0",primary:"#4488cc"}),dark:N({fg:"#c6c6c6",bg:"#444444",primary:"#88ccee"})}},{name:"sepia",label:"Sepia",colors:{light:R({fg:"#5b4636",bg:"#f1e8d0",primary:"#008b8b"}),dark:N({fg:"#ffd595",bg:"#342e25",primary:"#48d1cc"})}},{name:"grass",label:"Grass",colors:{light:R({fg:"#232c16",bg:"#d7dbbd",primary:"#177b4d"}),dark:N({fg:"#d8deba",bg:"#333627",primary:"#a6d608"})}},{name:"cherry",label:"Cherry",colors:{light:R({fg:"#4e1609",bg:"#f0d1d5",primary:"#de3838"}),dark:N({fg:"#e5c4c8",bg:"#462f32",primary:"#ff646e"})}},{name:"sky",label:"Sky",colors:{light:R({fg:"#262d48",bg:"#cedef5",primary:"#2d53e5"}),dark:N({fg:"#babee1",bg:"#282e47",primary:"#ff646e"})}},{name:"solarized",label:"Solarized",colors:{light:R({fg:"#586e75",bg:"#fdf6e3",primary:"#268bd2"}),dark:N({fg:"#93a1a1",bg:"#002b36",primary:"#268bd2"})}},{name:"gruvbox",label:"Gruvbox",colors:{light:R({fg:"#3c3836",bg:"#fbf1c7",primary:"#076678"}),dark:N({fg:"#ebdbb2",bg:"#282828",primary:"#83a598"})}},{name:"nord",label:"Nord",colors:{light:R({fg:"#2e3440",bg:"#eceff4",primary:"#5e81ac"}),dark:N({fg:"#d8dee9",bg:"#2e3440",primary:"#88c0d0"})}},{name:"contrast",label:"Contrast",colors:{light:R({fg:"#000000",bg:"#ffffff",primary:"#4488cc"}),dark:N({fg:"#ffffff",bg:"#000000",primary:"#88ccee"})}},{name:"sunset",label:"Sunset",colors:{light:R({fg:"#423126",bg:"#fff7f0",primary:"#fe6b64"}),dark:N({fg:"#f6e1d7",bg:"#3c2b25",primary:"#ff9c94"})}}],D=function(t){let e=arguments.length>1&&void 0!==arguments[1]&&arguments[1],a=`
    --b1: ${F(t["base-100"])};
    --b2: ${F(t["base-200"])};
    --b3: ${F(t["base-300"])};
    --bc: ${F(t["base-content"])};
    
    --p: ${F(t.primary)};
    --pc: ${O(t.primary)};
    
    --s: ${F(t.secondary)};
    --sc: ${O(t.secondary)};
    
    --a: ${F(t.accent)};
    --ac: ${O(t.accent)};
    
    --n: ${F(t.neutral)};
    --nc: ${F(t["neutral-content"])};
    
    --in: 69.37% 0.047 231deg;
    --inc: 100% 0 0deg;
    --su: 78.15% 0.12 160deg;
    --suc: 100% 0 0deg;
    --wa: 90.69% 0.123 84deg;
    --wac: 0% 0 0deg;
    --er: 70.9% 0.184 22deg;
    --erc: 100% 0 0deg;
  `,n=`
    --fallback-b1: ${t["base-100"]};
    --fallback-b2: ${t["base-200"]};
    --fallback-b3: ${t["base-300"]};
    --fallback-bc: ${t["base-content"]};

    --fallback-p: ${t.primary};
    --fallback-pc: ${T(t.primary)};

    --fallback-s: ${t.secondary};
    --fallback-sc: ${T(t.secondary)};

    --fallback-a: ${t.accent};
    --fallback-ac: ${T(t.accent)};

    --fallback-n: ${t.neutral};
    --fallback-nc: ${t["neutral-content"]};

    --fallback-in: #ff0000;
    --fallback-inc: #ffffff;
    --fallback-su: #00ff00;
    --fallback-suc: #000000;
    --fallback-wa: #ffff00;
    --fallback-wac: #000000;
    --fallback-er: #ff8000;
    --fallback-erc: #000000;
  `;return a+(e?n:"")};t.s(["applyCustomTheme",0,function(t,e){let a=arguments.length>2&&void 0!==arguments[2]&&arguments[2];if(!t&&!e)return;let n=t?`${t.name}-light`:`${e}-light`,i=t?`${t.name}-dark`:`${e}-dark`,r=t?R(t.colors.light):(P.find(t=>t.name===e)||P[0]).colors.light,o=t?N(t.colors.dark):(P.find(t=>t.name===e)||P[0]).colors.dark,l=`
    [data-theme="${n}"] {
      ${D(r,a)}
    }
    
    [data-theme="${i}"] {
      ${D(o,a)}
    }
    
    :root {
      --${n}: 1;
      --${i}: 1;
    }
  `,c=document.createElement("style");c.id=`theme-${t?t.name:e}-styles`,c.textContent=l;let h=document.getElementById(c.id);return h&&h.remove(),document.head.appendChild(c),{light:n,dark:i}},"generateDarkPalette",0,N,"generateLightPalette",0,R,"themes",0,P],431270);var j=t.i(201702),W=t.i(755678),K=t.i(651074);let q=[{family:"Bitter",weights:"ital,wght@0,100..900;1,100..900"},{family:"Fira Code",weights:"wght@300..700"},{family:"Literata",weights:"ital,opsz,wght@0,7..72,200..900;1,7..72,200..900"},{family:"Merriweather",weights:"ital,opsz,wght@0,18..144,300..900;1,18..144,300..900"},{family:"Noto Sans",weights:"ital,wght@0,100..900;1,100..900"},{family:"Open Sans",weights:"ital,wght@0,300..800;1,300..800"},{family:"Roboto",weights:"ital,wght@0,100..900;1,100..900"},{family:"Roboto Slab",weights:"ital,wght@0,100..900;1,100..900"},{family:"Vollkorn",weights:"ital,wght@0,400..900;1,400..900"},{family:"PT Sans",weights:"ital,wght@0,400;0,700;1,400;1,700"},{family:"PT Serif",weights:"ital,wght@0,400;0,700;1,400;1,700"},{family:"PT Mono",weights:""}],U=[{family:"LXGW WenKai TC",weights:""},{family:"Noto Sans SC",weights:""},{family:"Noto Sans TC",weights:""},{family:"Noto Serif JP",weights:""}],J=async function(t){let e=arguments.length>1&&void 0!==arguments[1]&&arguments[1],a=e||(0,j.isCJKEnv)(),n=`
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?${q.map(t=>{let{family:e,weights:a}=t;return`family=${encodeURIComponent(e)}${a?`:${a}`:""}`}).join("&")}&display=swap" crossorigin="anonymous">
`,i="";if(a&&(i=`
  @font-face {
    font-family: "FangSong";
    font-display: swap;
    src: local("Fang Song"), local("FangSong"), local("Noto Serif CJK"), local("Source Han Serif SC VF"), url("https://db.onlinewebfonts.com/t/2ecbfe1d9bfc191c6f15c0ccc23cbd43.eot");
    src: url("https://db.onlinewebfonts.com/t/2ecbfe1d9bfc191c6f15c0ccc23cbd43.eot?#iefix") format("embedded-opentype"),
    url("https://db.onlinewebfonts.com/t/2ecbfe1d9bfc191c6f15c0ccc23cbd43.woff2") format("woff2"),
    url("https://db.onlinewebfonts.com/t/2ecbfe1d9bfc191c6f15c0ccc23cbd43.woff") format("woff"),
    url("https://db.onlinewebfonts.com/t/2ecbfe1d9bfc191c6f15c0ccc23cbd43.ttf") format("truetype"),
    url("https://db.onlinewebfonts.com/t/2ecbfe1d9bfc191c6f15c0ccc23cbd43.svg#FangSong") format("svg");
  }
  @font-face {
    font-family: "Kaiti";
    font-display: swap;
    src: local("Kai"), local("KaiTi"), local("AR PL UKai"), local("LXGW WenKai GB Screen"), url("https://db.onlinewebfonts.com/t/1ee9941f1b8c128110ca4307dda59917.eot");
    src: url("https://db.onlinewebfonts.com/t/1ee9941f1b8c128110ca4307dda59917.eot?#iefix")format("embedded-opentype"),
    url("https://db.onlinewebfonts.com/t/1ee9941f1b8c128110ca4307dda59917.woff2")format("woff2"),
    url("https://db.onlinewebfonts.com/t/1ee9941f1b8c128110ca4307dda59917.woff")format("woff"),
    url("https://db.onlinewebfonts.com/t/1ee9941f1b8c128110ca4307dda59917.ttf")format("truetype"),
    url("https://db.onlinewebfonts.com/t/1ee9941f1b8c128110ca4307dda59917.svg#STKaiti")format("svg");
  }
  @font-face {
    font-family: "Heiti";
    font-display: swap;
    src: local("Hei"), local("SimHei"), local("WenQuanYi Zen Hei"), local("Source Han Sans SC VF"), url("https://db.onlinewebfonts.com/t/a4948b9d43a91468825a5251df1ec58d.eot");
    src: url("https://db.onlinewebfonts.com/t/a4948b9d43a91468825a5251df1ec58d.eot?#iefix")format("embedded-opentype"),
    url("https://db.onlinewebfonts.com/t/a4948b9d43a91468825a5251df1ec58d.woff2")format("woff2"),
    url("https://db.onlinewebfonts.com/t/a4948b9d43a91468825a5251df1ec58d.woff")format("woff"),
    url("https://db.onlinewebfonts.com/t/a4948b9d43a91468825a5251df1ec58d.ttf")format("truetype"),
    url("https://db.onlinewebfonts.com/t/a4948b9d43a91468825a5251df1ec58d.svg#WenQuanYi Micro Hei")format("svg");
  }
  @font-face {
    font-family: "XiHeiti";
    font-display: swap;
    src: local("PingFang SC"), local("Microsoft YaHei"), local("WenQuanYi Micro Hei"), local("FZHei-B01"), url("https://db.onlinewebfonts.com/t/4f0b783ba4a1b381fc7e7af81ecab481.eot");
    src: url("https://db.onlinewebfonts.com/t/4f0b783ba4a1b381fc7e7af81ecab481.eot?#iefix")format("embedded-opentype"),
    url("https://db.onlinewebfonts.com/t/4f0b783ba4a1b381fc7e7af81ecab481.woff2")format("woff2"),
    url("https://db.onlinewebfonts.com/t/4f0b783ba4a1b381fc7e7af81ecab481.woff")format("woff"),
    url("https://db.onlinewebfonts.com/t/4f0b783ba4a1b381fc7e7af81ecab481.ttf")format("truetype"),
    url("https://db.onlinewebfonts.com/t/4f0b783ba4a1b381fc7e7af81ecab481.svg#STHeiti J Light")format("svg");
}
`,n=`${n}

  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/misans-webfont@1.0.4/misans-l3/misans-l3/result.min.css" crossorigin="anonymous" />
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/lxgw-wenkai-screen-web/1.520.0/lxgwwenkaigbscreen/result.css" crossorigin="anonymous" />
  <link rel="stylesheet" href="https://ik.imagekit.io/fonts14/packages/GuanKiapTsingKhai/dist/GuanKiapTsingKhai-T/result.css" crossorigin="anonymous" />
  <link rel="stylesheet" href="https://ik.imagekit.io/fonts14/packages/syst/dist/SourceHanSerifCN/result.css" crossorigin="anonymous" />
  <link rel="stylesheet" href="https://ik.imagekit.io/fonts14/packages/hwmct/dist/%E6%B1%87%E6%96%87%E6%98%8E%E6%9C%9D%E4%BD%93/result.css" crossorigin="anonymous" />
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?${U.map(t=>{let{family:e,weights:a}=t;return`family=${encodeURIComponent(e)}${a?`:${a}`:""}`}).join("&")}&display=swap" crossorigin="anonymous" />
`),i){let e=t.createElement("style");e.textContent=i,t.head.appendChild(e)}Array.from(new DOMParser().parseFromString(n,"text/html").head.children).forEach(e=>{if("LINK"===e.tagName){let a=t.createElement("link");a.rel=e.getAttribute("rel")||"",a.href=e.getAttribute("href")||"",a.crossOrigin=e.getAttribute("crossorigin")||"",t.head.appendChild(a)}})};function Y(t){switch(t.toLowerCase().split(".").pop()){case"ttf":default:return"ttf";case"otf":return"otf";case"woff":return"woff";case"woff2":return"woff2"}}function X(t){let e={ttf:"truetype",otf:"opentype",woff:"woff",woff2:"woff2"}[Y(t.path)]||"truetype",a=(t.family||t.name).replace(/\s+/g," ").trim(),n=t.style||"normal",i=t.weight||400,r=t.variable||!1;if(!t.blobUrl)throw Error(`Blob URL not available for font: ${t.name}`);return`
    @font-face {
      font-family: "${a}";
      ${r?"":`font-style: ${n};`}
      ${r?"":`font-weight: ${i};`}
      src: url("${t.blobUrl}") format("${e}");
      font-display: swap;
    }
  `}t.s(["createCustomFont",0,function(t,e){let a=e?.name||(0,W.getFilename)(t).replace(/\.(ttf|otf|woff|woff2)$/i,"");return{...e,id:(0,K.md5Fingerprint)(a),name:a,path:t}},"createFontCSS",0,X,"getFontFormat",0,Y,"getMimeType",0,function(t){return({ttf:"font/ttf",otf:"font/otf",woff:"font/woff",woff2:"font/woff2"})[t]||"font/ttf"},"mountAdditionalFonts",0,J,"mountCustomFont",0,(t,e)=>{let a=`custom-font-${e.id}`,n=t.getElementById(a)||t.createElement("style");n.id=a,n.textContent=X(e),n.parentNode||t.head.appendChild(n)}],727476);let Z="scroll-wrapper",Q="scroll-wrapper-fit",tt=`.${Z}`,te="data-readest-scroll-wrapper-touch-scroll",ta=t=>t.scrollWidth-t.clientWidth>4,tn=t=>t.scrollHeight-t.clientHeight>4,ti=t=>{if(!t||!("closest"in t))return null;let e=t.closest(tt);for(;e;){if(ta(e)||tn(e))return e;e=e.parentElement?.closest(tt)??null}return null},tr=["Top","Right","Bottom","Left"];t.s(["SCROLL_WRAPPER_CLASS",0,Z,"SCROLL_WRAPPER_FIT_CLASS",0,Q,"applyScrollableStyle",0,t=>{let e=t.defaultView,a=a=>{let n=a.parentElement;if(!n||n.classList.contains(Z))return;let i=t.createElement("div");i.className=Z,i.setAttribute("cfi-skip",""),n.insertBefore(i,a),i.appendChild(a),((t,e,a)=>{if(!a)return;let n=t.style;if(!n)return;let i=a.getComputedStyle(t);for(let t of tr){let a=`margin${t}`,r=i[a];0>parseFloat(r)&&(e.style[a]=r,n[a]="0px")}})(a,i,e),((t,e)=>{if(!e?.ResizeObserver)return;let a=new e.ResizeObserver(()=>{if(!(t.clientWidth<=0)){let e;e=t.scrollWidth-t.clientWidth<=4,t.classList.toggle(Q,e),a.disconnect()}});a.observe(t)})(i,e)};t.querySelectorAll("table").forEach(a),t.querySelectorAll("math").forEach(t=>{(t=>{if("block"===t.getAttribute("display"))return!0;let e=t.parentElement;if(!e)return!1;for(let a of e.childNodes)if(a!==t&&(a.nodeType===Node.ELEMENT_NODE||a.nodeType===Node.TEXT_NODE&&a.textContent?.trim()))return!1;return!0})(t)&&a(t)})},"applyTableTouchScroll",0,t=>{let e=t.documentElement;if("true"===e.getAttribute(te))return;e.setAttribute(te,"true");let a=0,n=0,i=null,r=()=>{i=null},o={capture:!0,passive:!1};t.addEventListener("touchstart",t=>{if(!(i=ti(t.target)))return;let e=t.changedTouches[0];e&&(a=e.screenX,n=e.screenY)},o),t.addEventListener("touchmove",t=>{var e;if(!i||!i.contains(t.target))return;let r=t.changedTouches[0];if(!r)return;let o=r.screenX-a,l=r.screenY-n;e=i,(Math.abs(o)>Math.abs(l)?Math.abs(o)>=8&&ta(e):Math.abs(l)>=8&&tn(e))&&t.stopImmediatePropagation()},o),t.addEventListener("touchend",r,o),t.addEventListener("touchcancel",r,o),t.addEventListener("wheel",t=>{let e=ti(t.target);e&&(Math.abs(t.deltaX)>Math.abs(t.deltaY)?ta(e):tn(e))&&t.stopImmediatePropagation()},{capture:!0,passive:!0})}],162755);let to=(t,e,a,n)=>{let r=["Georgia","Times New Roman"],o=[t,...n!==t?[n]:[],...i.SERIF_FONTS.filter(e=>e!==t&&e!==n&&!r.includes(e)),...i.CJK_SERIF_FONTS.filter(e=>e!==t&&e!==n),...r.filter(t=>i.SERIF_FONTS.includes(t)&&!r.includes(n)),...i.FALLBACK_FONTS],l=[e,...n!==e?[n]:[],...i.SANS_SERIF_FONTS.filter(t=>t!==e&&t!==n),...i.CJK_SANS_SERIF_FONTS.filter(t=>t!==e&&t!==n),...i.FALLBACK_FONTS],c=[a,...i.MONOSPACE_FONTS.filter(t=>t!==a)],h=t=>t.map(t=>`"${t}"`).join(", ");return{serif:`${h(o)}, serif`,sansSerif:`${h(l)}, sans-serif`,monospace:`${h(c)}, monospace`}},tl=()=>`
    ::selection {
      color: var(--theme-bg-color);
      background: var(--theme-fg-color);
    }
    ::-moz-selection {
      color: var(--theme-bg-color);
      background: var(--theme-fg-color);
    }
  `,tc=t=>`
  .translation-source {
  }
  .translation-target {
  }
  .translation-target.hidden {
    display: none !important;
  }
  .translation-target-block {
    display: block !important;
    ${t?"margin: 0.5em 0 !important;":""}
  }
  .translation-target-toc {
    display: block !important;
    overflow: hidden;
    text-overflow: ellipsis;
  }
`,th=()=>{let t="auto",e="default",a=!1,n=[];e=localStorage.getItem("themeColor")||"default",t=localStorage.getItem("themeMode")||"auto",a="true"===localStorage.getItem("systemIsDarkMode"),n=JSON.parse(localStorage.getItem("customThemes")||"[]");let i="dark"===t||"auto"===t&&a,r=P.find(t=>t.name===e);if(!r){let t=n.find(t=>t.name===e);t&&(r={name:t.name,label:t.label,colors:{light:R(t.colors.light),dark:N(t.colors.dark)}})}r||(r=P[0]);let o=i?r.colors.dark:r.colors.light;return{bg:o["base-100"],fg:o["base-content"],primary:o.primary,palette:o,isDarkMode:i}};t.s(["applyFixedlayoutStyles",0,(t,e,a)=>{a||(a=th());let{bg:n,fg:i,primary:r,isDarkMode:o}=a,l=e.isEink,c=e.overrideColor,h=e.invertImgColorInDark,s=e.contrast??100,d=[];o&&h&&d.push("invert(100%)"),100!==s&&d.push(`contrast(${s}%)`);let g=d.length?`filter: ${d.join(" ")};`:"",f="fixed-layout-styles",u=t.getElementById(f);u&&u.remove(),(u=t.createElement("style")).id=f,u.textContent=`
    html {
      --theme-bg-color: ${n};
      --theme-fg-color: ${i};
      --theme-primary-color: ${r};
      color-scheme: ${o?"dark":"light"};
    }
    body {
      position: relative;
      background-color: var(--theme-bg-color);
    }
    ${l?tl():""}
    #canvas {
      display: inline-block;
      width: fit-content;
      height: fit-content;
      background-color: var(--theme-bg-color);
    }
    img, canvas {
      ${g}
      ${c?`mix-blend-mode: ${o?"#000000"===n?"luminosity":"overlay":"multiply"};`:""}
    }
    img.singlePage {
      position: relative;
    }
  `,t.head.appendChild(u)},"applyImageStyle",0,t=>{let e=t.defaultView??window;for(let{img:a,percentWidth:n,percentHeight:i,inlineWithText:r,keepBaseline:o}of Array.from(t.querySelectorAll("img")).map(t=>{let a=t.getAttribute("width"),n=a&&(a.endsWith("%")||a.endsWith("vw"))?parseFloat(a):NaN,i=t.getAttribute("height"),r=i&&(i.endsWith("%")||i.endsWith("vh"))?parseFloat(i):NaN,o=!1,l=!1,c=t.parentNode;if(c&&c.nodeType===Node.ELEMENT_NODE){let a=Array.from(c.childNodes),n=a.some(t=>t.nodeType===Node.TEXT_NODE&&t.textContent?.trim()),i=a.every(t=>t.nodeType!==Node.ELEMENT_NODE||"BR"!==t.tagName);if(o=n&&i){let a=e.getComputedStyle(t).verticalAlign;l=""===a||"baseline"===a}}return{img:t,percentWidth:n,percentHeight:r,inlineWithText:o,keepBaseline:l}}))isNaN(n)||(a.style.width=`${n/100*window.innerWidth}px`,a.removeAttribute("width")),isNaN(i)||(a.style.height=`${i/100*window.innerHeight}px`,a.removeAttribute("height")),r&&(a.classList.add("has-text-siblings"),o&&a.classList.add("has-text-siblings-baseline"));t.querySelectorAll("hr").forEach(t=>{let e=window.getComputedStyle(t);e.backgroundImage&&"none"!==e.backgroundImage&&t.classList.add("background-img")})},"applyScrollModeClass",0,(t,e)=>{t.body.classList.remove("scroll-mode","paginated-mode"),t.body.classList.add(e?"scroll-mode":"paginated-mode")},"applyScrollbarStyle",0,(t,e)=>{let a="scrollbar-hide-style",n=t.getElementById(a);e?(n||((n=t.createElement("style")).id=a,t.head.appendChild(n)),n.textContent="foliate-view::part(container) { scrollbar-width: none; }"):n&&(n.textContent="foliate-view::part(container) { scrollbar-width: thin; }")},"applyThemeModeClass",0,(t,e)=>{t.body.classList.remove("theme-light","theme-dark"),t.body.classList.add(e?"theme-dark":"theme-light")},"applyTranslationStyle",0,t=>{let e="translation-style",a=document.getElementById(e);a&&a.remove();let n=document.createElement("style");n.id=e,n.textContent=tc(t.showTranslateSource),document.head.appendChild(n)},"getBaseFontFamily",0,t=>{let e=to(t.serifFont,t.sansSerifFont,t.monospaceFont,t.defaultCJKFont);return"serif"===t.defaultFont.toLowerCase()?e.serif:e.sansSerif},"getDictStyles",0,(t,e,a)=>`
    a:empty {
      background-color: transparent;
      mix-blend-mode: multiply;
    }
    a img {
      mix-blend-mode: multiply;
    }
    div[data-dict-kind="mdict"] .entry_name {
      font-size: 1.2em;
      margin-block-start: 0.5em;
      margin-block-end: 0.5em;
    }
    div[data-dict-kind="mdict"] .juan_drop {
      ${a?`background-color: color-mix(in srgb, ${t} 80%, #000);`:""}
    }
  `,"getFootnoteStyles",0,()=>`
  .duokan-footnote-content,
  .duokan-footnote-item {
    display: block !important;
  }

  body {
    padding: 1em !important;
    overflow-wrap: break-word;
  }

  a:any-link {
    text-decoration: none;
    padding: unset;
    margin: unset;
  }

  ol {
    margin: 0;
    padding: 0;
  }

  p, li, blockquote, dd {
    margin: unset !important;
    text-indent: unset !important;
  }

  div {
    margin: unset !important;
    padding: unset !important;
  }

  dt {
    font-weight: bold;
    line-height: 1.6;
  }

  .epubtype-footnote,
  aside[epub|type~="endnote"],
  aside[epub|type~="footnote"],
  aside[epub|type~="note"],
  aside[epub|type~="rearnote"] {
    display: block;
  }
`,"getStyles",0,function(t,e){var a,n,i,r,o,l,c,h,s;let d,g,f,u,p,m,v,b,w,M,y,z,x,k,H,$,S,I,A,L=arguments.length>2&&void 0!==arguments[2]?arguments[2]:[];e||(e=th());let _=(d=t.marginTopPx,g=t.marginRightPx,f=t.marginBottomPx,u=t.marginLeftPx,p=t.writingMode,m=t.vertical,`
  html {
    --margin-top: ${d}px;
    --margin-right: ${g}px;
    --margin-bottom: ${f}px;
    --margin-left: ${u}px;
  }
  html, body {
    ${"auto"===p?"":`writing-mode: ${p} !important;`}
    max-height: unset;
    -webkit-touch-callout: none;
    -webkit-user-select: text;
  }
  body {
    overflow: unset;
    zoom: 1;
    padding: unset;
    margin: unset;
  }
  /* -webkit-touch-callout on html/body does not reach descendant images in
     Android WebView, and the native image callout collides with the reader's
     touch handlers and can freeze the app */
  img {
    -webkit-touch-callout: none;
    -webkit-user-drag: none;
  }
  svg:where(:not([width])), img:where(:not([width])) {
    width: auto;
  }
  svg:where(:not([height])), img:where(:not([height])) {
    height: auto;
  }
  figure > div:has(img) {
    height: auto !important;
  }
  /* enlarge the clickable area of links */
  a {
    position: relative !important;
  }
  a::before {
    content: '';
    position: absolute;
    inset: -10px;
  }

  .${Z} {
    display: block;
    overflow: auto;
    max-width: 100%;
    touch-action: pan-x pan-y;
    scrollbar-width: thin;
    -webkit-overflow-scrolling: touch;
  }
  .${Q} {
    overflow: visible;
  }
  .${Z} > table {
    display: table !important;
    max-width: 100%;
  }
  /* MathML is usually pretty-printed: with pre-wrap the newlines and
     indentation between the tokens become rendered line breaks, and every
     inline formula ends up on its own line. */
  pre, code {
    white-space: pre-wrap !important;
    scrollbar-width: none;
  }
  math {
    overflow: auto;
    scrollbar-width: none;
  }
  table, math {
    max-width: calc(var(--available-width) * 1px);
    max-height: calc(var(--available-height) * 1px);
  }

  .epubtype-footnote,
  aside[epub|type~="endnote"],
  aside[epub|type~="footnote"],
  aside[epub|type~="note"],
  aside[epub|type~="rearnote"] {
    display: none;
  }

  /* Now begins really dirty hacks to fix some badly designed epubs */
  body {
    line-height: unset;
  }

  .duokan-footnote-content,
  .duokan-footnote-item {
    display: none;
  }

  .duokan-image-gallery-cell {
    height: calc(var(--available-height) * 1px);
  }

  .duokan-image-gallery-cell img {
    height: 90%;
  }

  div:has(> img, > svg) {
    max-width: 100% !important;
  }

  body.paginated-mode td:has(img), body.paginated-mode td :has(img) {
    max-height: calc(var(--available-height) * 0.8 * 1px);
  }

  figure.code {
    overflow: unset !important;
  }

  /* some epubs set insane inline-block for p */
  p {
    display: block;
  }

  /* inline images without dimension */
  .ie6 img {
    width: unset;
    height: unset;
  }
  sup img {
    height: 1em;
  }
  img.has-text-siblings {
    ${m?"width: 1em;":"height: 1em;"}
  }
  /* Baseline is only Readest's default: applyImageStyle adds this class when the
     book leaves vertical-align at its initial value, so an author-set value
     (e.g. a CJK glyph-substitution image nudged with vertical-align: -0.15em)
     keeps winning. See #4866. */
  img.has-text-siblings-baseline {
    vertical-align: baseline;
  }
  :is(div) > img.has-text-siblings[style*="object-fit"] {
    display: block;
    height: auto;
    vertical-align: unset;
  }
  .duokan-footnote img:not([class]) {
    width: 0.8em;
    height: 0.8em;
  }
  div:has(img.singlepage) {
    position: relative;
    width: auto;
    height: auto;
  }
  /* some mobi */
  p[width][height] > img:only-child {
    width: unset !important;
    height: unset !important;
  }

  /* page break */
  body.paginated-mode div[style*="page-break-after: always"],
  body.paginated-mode div[style*="page-break-after:always"],
  body.paginated-mode p[style*="page-break-after: always"],
  body.paginated-mode p[style*="page-break-after:always"] {
    margin-bottom: calc(var(--available-height) * 1px);
  }

  .br {
    display: flow-root;
  }

  .h5_mainbody {
    overflow: unset !important;
  }
`),C=t.useBookLayout?"":(v=t.overrideLayout,b=t.paragraphMargin,w=t.lineHeight,M=t.wordSpacing,y=t.letterSpacing,z=t.textIndent,x=t.fullJustification,k=t.hyphenation,H=t.vertical,`
  html {
    --default-text-align: ${x?"justify":"start"};
    hanging-punctuation: allow-end last;
    orphans: 2;
    widows: 2;
  }
  html, body {
    text-align: var(--default-text-align);
  }
  [align="left"] { text-align: left; }
  [align="right"] { text-align: right; }
  [align="center"] { text-align: center; }
  [align="justify"] { text-align: justify; }
  :is(hgroup, header) p {
      text-align: unset;
      hyphens: unset;
  }
  p, blockquote, dd, div:not(:has(*:not(b, a, em, i, strong, u, span))) {
    line-height: ${w} ${v?"!important":""};
    word-spacing: ${M}px ${v?"!important":""};
    letter-spacing: ${y}px ${v?"!important":""};
    text-indent: ${z}em ${v?"!important":""};
    -webkit-hyphens: ${k?"auto":"manual"} ${v?"!important":""};
    hyphens: ${k?"auto":"manual"} ${v?"!important":""};
    -webkit-hyphenate-limit-before: 3;
    -webkit-hyphenate-limit-after: 2;
    -webkit-hyphenate-limit-lines: 2;
    hanging-punctuation: allow-end last;
    widows: 2;
  }
  li {
    line-height: ${w} ${v?"!important":""};
    -webkit-hyphens: ${k?"auto":"manual"} ${v?"!important":""};
    hyphens: ${k?"auto":"manual"} ${v?"!important":""};
  }
  p.aligned-center, blockquote.aligned-center,
  dd.aligned-center, div.aligned-center {
    text-align: center ${v?"!important":""};
  }
  p.aligned-left, blockquote.aligned-left,
  dd.aligned-left, div.aligned-left {
    ${x&&v?"text-align: justify !important;":""}
  }
  p.aligned-right, blockquote.aligned-right,
  dd.aligned-right, div.aligned-right {
    text-align: right ${v?"!important":""};
  }
  p.aligned-justify, blockquote.aligned-justify,
  dd.aligned-justify, div.aligned-justify {
    ${!x&&v?"text-align: initial !important;":""};
  }
  p:has(> img:only-child), p:has(> :only-child > img:only-child),
  p:has(> img:not(.has-text-siblings)),
  p:has(> a:first-child + img:last-child) {
    text-indent: initial !important;
  }
  blockquote[align="center"], div[align="center"],
  p[align="center"], dd[align="center"],
  p.aligned-center, blockquote.aligned-center,
  dd.aligned-center, div.aligned-center,
  li p, ol p, ul p, td p {
    text-indent: initial !important;
  }
  p {
    ${H?`margin-left: ${b}em ${v?"!important":""};`:""}
    ${H?`margin-right: ${b}em ${v?"!important":""};`:""}
    ${H?`margin-top: unset ${v?"!important":""};`:""}
    ${H?`margin-bottom: unset ${v?"!important":""};`:""}
    ${!H?`margin-top: ${b}em ${v?"!important":""};`:""}
    ${!H?`margin-bottom: ${b}em ${v?"!important":""};`:""}
    ${!H?`margin-left: unset ${v?"!important":""};`:""}
    ${!H?`margin-right: unset ${v?"!important":""};`:""}
  }
  div {
    ${H&&v?`margin-left: ${b}em !important;`:""}
    ${H&&v?`margin-right: ${b}em !important;`:""}
    ${!H&&v?`margin-top: ${b}em !important;`:""}
    ${!H&&v?`margin-bottom: ${b}em !important;`:""}
  }
  p > font:only-child {
    display: flow-root;
  }

  :lang(zh), :lang(ja), :lang(ko) {
    widows: 1;
    orphans: 1;
  }

  /* workaround for some badly designed epubs */
  div.left *, p.left * { text-align: left; }
  div.right *, p.right * { text-align: right; }
  div.center *, p.center * { text-align: center; }
  div.justify *, p.justify * { text-align: justify; }

  img.pi {
    ${H?"transform: rotate(90deg);":""}
    ${H?"transform-origin: center;":""}
    ${H?"height: 2em;":""}
    ${H?`width: ${w}em;`:""}
    ${H?"vertical-align: unset;":""}
  }

  .nonindent, .noindent {
    text-indent: unset !important;
  }
`),V=["ios","android"].includes((0,j.getOSPlatform)()),B=(t.zoomLevel||100)/100,G=(a=t.serifFont,n=t.sansSerifFont,i=t.monospaceFont,r=t.defaultFont,o=t.defaultCJKFont,l=t.defaultFontSize*(V?1.25:1)*B,c=t.minimumFontSize,h=t.fontWeight,s=t.overrideFont,$=to(a,n,i,o),S="serif"===r.toLowerCase()?"--serif":"--sans-serif",`
    html {
      --serif: ${$.serif};
      --sans-serif: ${$.sansSerif};
      --monospace: ${$.monospace};
      --font-size: ${l}px;
      --min-font-size: ${c}px;
      --font-weight: ${h};
    }
    html, body {
      font-size: ${l}px !important;
      font-weight: ${h};
      -webkit-text-size-adjust: none;
      text-size-adjust: none;
    }
    /* lower specificity than ebook built-in font styles */
    html {
      font-family: var(${S}) ${s?"!important":""};
    }
    /* higher specificity than ebook built-in font styles */
    html body {
      ${s?`font-family: var(${S}) !important;`:""}
    }
    font[size="1"] {
      font-size: ${c}px;
    }
    font[size="2"] {
      font-size: ${1.5*c}px;
    }
    font[size="3"] {
      font-size: ${l}px;
    }
    font[size="4"] {
      font-size: ${1.2*l}px;
    }
    font[size="5"] {
      font-size: ${1.5*l}px;
    }
    font[size="6"] {
      font-size: ${2*l}px;
    }
    font[size="7"] {
      font-size: ${3*l}px;
    }
    /* hardcoded inline font size */
    [style*="font-size: 16px"], [style*="font-size:16px"] {
      font-size: 1rem !important;
    }
    pre, code, kbd {
      font-family: var(--monospace);
      font-variant-ligatures: none;
    }
    body *:not(pre, code, kbd, .code):not(pre *, code *, kbd *, .code *) {
      ${s?"font-family: revert !important;":""}
    }
  `),E=L.filter(t=>!!t.blobUrl).map(t=>{try{return X(t)}catch{return""}}).join("\n"),F=((t,e,a,n,i)=>{let{bg:r,fg:o,primary:l,isDarkMode:c}=a,h=!!n&&"none"!==n;return`
    html {
      --bg-texture-id: ${n};
      --theme-bg-color: ${r};
      --theme-fg-color: ${o};
      --theme-primary-color: ${l};
      --override-color: ${t};
      color-scheme: ${c?"dark":"light"};
    }
    html, body {
      color: ${o};
    }
    ${i?tl():""}
    html[has-background], body[has-background] {
      --background-set: var(--theme-bg-color);
    }
    html {
      background-color: var(--theme-bg-color, transparent);
      background: var(--background-set, none);
    }
    body {
      ${i?`background-color: ${r} !important;`:""}
    }
    section, aside, blockquote, article, nav, header, footer, main, figure,
    div, p, font, h1, h2, h3, h4, h5, h6, li, span {
      ${t&&!h?`background-color: ${r} !important;`:""}
      ${t&&!h?`color: ${o} !important;`:""}
      ${t&&!h?`border-color: ${o} !important;`:""}
    }
    pre, span { /* inline code blocks */
      ${t?`background-color: ${r} !important;`:""}
    }
    a:any-link {
      ${t?`color: ${l} !important;`:c?"color: lightblue;":""}
      text-decoration: ${i?"underline":"none"};
    }
    body.pbg {
      ${c?`background-color: ${r} !important;`:""}
    }
    img {
      ${c&&e?"filter: invert(100%);":""}
      ${c&&t?"filter: grayscale(100%) contrast(1.2) brightness(1.2);":""}
      ${t?"mix-blend-mode: multiply;":""}
    }
    svg, img {
      ${t?"background-color: transparent !important;":""};
    }
    /* horizontal rule #1649 */
    *:has(> hr.background-img):not(body) {
      background-color: ${r};
    }
    hr.background-img {
      mix-blend-mode: multiply;
    }
    p[width][height] > img:only-child {
      mix-blend-mode: multiply;
    }
    /* inline images */
    *:has(> img.has-text-siblings):not(body) {
      ${t?`background-color: ${r};`:""}
    }
    p img.has-text-siblings, span img.has-text-siblings, sup img.has-text-siblings {
      mix-blend-mode: ${c?"screen":"multiply"};
    }
    table:has(> colgroup) {
      table-layout: fixed;
    }
    td, th {
      word-break: break-word;
      overflow-wrap: anywhere;
    }
    /* code */
    body.theme-dark code {
      ${c?`color: ${o}cc;`:""}
      ${c?`background: color-mix(in srgb, ${r} 90%, #000);`:""}
      ${c?`background-color: color-mix(in srgb, ${r} 90%, #000);`:""}
    }
    blockquote {
      ${c?`background: color-mix(in srgb, ${r} 80%, #000);`:""}
    }
    /* Only tint table descendants when the user has opted into color override.
       By default, leave them transparent so a plain table (and the invisible
       spacer cells some books use for vertical layout) keeps the page
       background instead of a different shade. Illegible light/zebra table
       backgrounds are handled separately by the dark-mode light-background
       rewriters (getDarkModeLightBackgroundOverrides / transformStylesheet).
       See #4419 (and #2377, which this gate originally fixed). */
    blockquote, table * {
      ${c&&t?`background: color-mix(in srgb, ${r} 80%, #000);`:""}
      ${c&&t?`background-color: color-mix(in srgb, ${r} 80%, #000);`:""}
    }
    /* override inline hardcoded text color */
    font[color="#000000"], font[color="#000"], font[color="black"],
    font[color="rgb(0,0,0)"], font[color="rgb(0, 0, 0)"],
    *[style*="color: rgb(0,0,0)"], *[style*="color: rgb(0, 0, 0)"],
    *[style*="color: #000"], *[style*="color: #000000"], *[style*="color: black"],
    *[style*="color:rgb(0,0,0)"], *[style*="color:rgb(0, 0, 0)"],
    *[style*="color:#000"], *[style*="color:#000000"], *[style*="color:black"] {
      color: ${o} !important;
    }
    ${c&&!t?`
    /* Callout boxes often use inline white/light backgrounds while html/body set dark fg. */
    *[style*="background-color: #fff"], *[style*="background-color:#fff"],
    *[style*="background-color: #ffffff"], *[style*="background-color:#ffffff"],
    *[style*="background-color: white"], *[style*="background-color:white"],
    *[style*="background: #fff"], *[style*="background:#fff"],
    *[style*="background: #ffffff"], *[style*="background:#ffffff"],
    *[style*="background: white"], *[style*="background:white"],
    *[style*="background-color: rgb(255"], *[style*="background-color:rgb(255"],
    *[style*="background: rgb(255"], *[style*="background:rgb(255"] {
      background-color: ${r} !important;
    }
    /* Force transparent, not the theme bg: the dark page fill already comes from
       the paginator container / reader grid cell, while an opaque body paints over
       the host background texture (#4446) — and foliate captures docBackground once
       per section load, so the body must stay transparent regardless of texture
       state. Book-forced light page backgrounds still get neutralized (#4392) since
       the theme-dark fill shows through. */
    body.theme-dark {
      background-color: transparent !important;
    }
`:""}
    /* for the Gutenberg eBooks */
    #pg-header * {
      color: inherit !important;
    }
    .x-ebookmaker, .x-ebookmaker-cover, .x-ebookmaker-coverpage {
      background-color: unset !important;
    }
    /* for the Feedbooks eBooks */
    .chapterHeader, .chapterHeader * {
      border-color: unset;
      background-color: ${r} !important;
    }
    .calibre {
      color: unset;
      background-color: unset;
    }
  `})(t.overrideColor,t.invertImgColorInDark,e,t.backgroundTextureId,t.isEink),O=tc(t.showTranslateSource),T=`
  /* Warichu (割注/夹注) — double-line inline annotation */
  .warichu-pending {
    display: inline;
    font-size: 0.5em;
    line-height: 1.1;
  }
  .warichu-chunk {
    display: inline-block;
    line-height: 1.1;
    font-size: 0.5em;
    text-indent: 0;
    vertical-align: middle !important;
    width: 1lh !important;
    text-align: center !important;
  }
  .warichu-chunk .warichu-line {
    display: inline;
  }
  .warichu-open,
  .warichu-close {
    display: inline;
    font-size: 0.5em;
    vertical-align: middle;
    line-height: 1.1;
  }
`,R=(I=t.wordLensGlossFontSize||.5,A=t.wordLensGlossColor||"",`
  rt {
    user-select: none;
    -webkit-user-select: none;
  }
  rp {
    display: none !important;
  }
  ruby.wl-gloss {
    cursor: help;
  }
  ruby.wl-gloss > rt {
    font-size: ${I}em;
    line-height: 1.1;
    ${A?`color: ${A};
    opacity: 1;`:"opacity: 0.7;"}
    font-weight: normal;
    text-align: center;
  }
`),N=t.userStylesheet;return`@namespace epub "http://www.idpf.org/2007/ops";
${E}
${_}
${C}
${G}
${F}
${O}
${T}
${R}
${N}`},"getThemeCode",0,th,"keepTextAlignment",0,t=>{let e=t.defaultView??window,a=t.querySelectorAll("div, p, blockquote, dd"),n=Array(a.length);for(let t=0;t<a.length;t++){let i=e.getComputedStyle(a[t]).textAlign;"center"===i?n[t]="aligned-center":"left"===i?n[t]="aligned-left":"right"===i?n[t]="aligned-right":"justify"===i?n[t]="aligned-justify":n[t]=null}for(let t=0;t<a.length;t++){let e=n[t];e&&a[t].classList.add(e)}},"transformStylesheet",0,(t,e,a,n)=>{let i=["ios","android"].includes((0,j.getOSPlatform)())?1.25:1,r=!t.includes("{"),o=/([^{]+)({[^}]+})/g;t=(t=t.replace(o,(t,e,a)=>{let n=/text-align\s*:\s*center\s*[;$]/.test(a),i=/text-indent\s*:\s*0(?:\.0+)?(?:px|em|rem|%)?\s*[;$]/.test(a);return n&&i?e+(a=(a=a.replace(/(text-align\s*:\s*center)(\s*;|\s*$)/g,"$1 !important$2")).replace(/(text-indent\s*:\s*0(?:\.0+)?(?:px|em|rem|%)?)(\s*;|\s*$)/g,"$1 !important$2")):t})).replace(o,(t,e,a)=>/white-space\s*:\s*nowrap\s*[;$]/.test(a)?(/overflow\s*:/.test(a)||(a=a.replace(/}$/," overflow: clip !important; }")),e+a):t),r?/page-break-after\s*:\s*always\s*[;]?/.test(t)&&!/margin-bottom\s*:/.test(t)&&(t=t.replace(/;?\s*$/,"")+"; margin-bottom: calc(var(--available-height) * 1px)"):t=t.replace(o,(t,e,a)=>/page-break-after\s*:\s*always\s*[;$]/.test(a)?(/margin-bottom\s*:/.test(a)||(a=a.replace(/}$/," margin-bottom: calc(var(--available-height) * 1px); }")),e+a):t),t=(t=(t=(t=t.replace(o,(t,e,a)=>{if(n)return e+a;let i=[],r=!1;for(let t of["top","bottom","left","right"]){let e=RegExp(`duokan-bleed\\s*:\\s*[^;]*${t}[^;]*;`),n=RegExp(`margin-${t}\\s*:`);e.test(a)&&!n.test(a)&&(r=!0,i.push(t),a=a.replace(/}$/,` margin-${t}: calc(-1 * var(--page-margin-${t})) !important; }`))}return r&&(/position\s*:/.test(a)||(a=a.replace(/}$/," position: relative !important; }")),/overflow\s*:/.test(a)||(a=a.replace(/}$/," overflow: hidden !important; }")),/display\s*:/.test(a)||(a=a.replace(/}$/," display: flow-root !important; }")),i.includes("left")&&i.includes("right")&&(a=a.replace(/}$/," width: calc(var(--full-width) * 1px) !important; }").replace(/}$/," min-width: calc(var(--full-width) * 1px) !important; }").replace(/}$/," max-width: calc(var(--full-width) * 1px) !important; }")),i.includes("top")&&i.includes("bottom")&&(a=a.replace(/}$/," height: calc(var(--full-height) * 1px) !important; }").replace(/}$/," min-height: calc(var(--full-height) * 1px) !important; }").replace(/}$/," max-height: calc(var(--full-height) * 1px) !important; }"))),e+a})).replace(o,(t,e,a)=>{if(/\bbody\b/i.test(e)){let t=/font-family\s*:\s*serif\s*(?:;|\}|$)/.test(a),e=/font-family\s*:\s*sans-serif\s*(?:;|\}|$)/.test(a);t&&(a=a.replace(/font-family\s*:\s*serif\s*(;|\}|$)/gi,"font-family: unset$1")),e&&(a=a.replace(/font-family\s*:\s*sans-serif\s*(;|\}|$)/gi,"font-family: unset$1"))}return e+a})).replace(o,(t,a,n)=>{let i=/(?:^|[^a-z-])width\s*:\s*(\d+(?:\.\d+)?)px/.exec(n);return(i?parseFloat(i[1]??"0"):0)>e&&!/max-width\s*:/.test(n)?a+(n=n.replace(/}$/," width: 100%; max-width: calc(var(--available-width) * 1px); box-sizing: border-box; }")):t})).replace(/font-size\s*:\s*xx-small/gi,"font-size: 0.6rem").replace(/font-size\s*:\s*x-small/gi,"font-size: 0.75rem").replace(/font-size\s*:\s*small/gi,"font-size: 0.875rem").replace(/font-size\s*:\s*medium/gi,"font-size: 1rem").replace(/font-size\s*:\s*large/gi,"font-size: 1.2rem").replace(/font-size\s*:\s*x-large/gi,"font-size: 1.5rem").replace(/font-size\s*:\s*xx-large/gi,"font-size: 2rem").replace(/font-size\s*:\s*xxx-large/gi,"font-size: 3rem").replace(/font-size\s*:\s*(\d+(?:\.\d+)?)px/gi,(t,e)=>{let a=parseFloat(e)/i/16;return`font-size: ${a}rem`}).replace(/font-size\s*:\s*(\d+(?:\.\d+)?)pt/gi,(t,e)=>{let a=parseFloat(e)/i/12;return`font-size: ${a}rem`}).replace(/font-size\s*:\s*(\d*\.?\d+)(px|rem|em|%)?/gi,function(t,e){let a=arguments.length>2&&void 0!==arguments[2]?arguments[2]:"px";return`font-size: max(${e}${a}, var(--min-font-size, 8px))`}).replace(/backdrop-filter\s*:\s*brightness\(100%\)\s*[;]?/gi,"").replace(/(\d*\.?\d+)vw/gi,(t,a)=>parseFloat(a)*e/100+"px").replace(/(\d*\.?\d+)vh/gi,(t,e)=>parseFloat(e)*a/100+"px").replace(/([\s;])-webkit-user-select\s*:\s*none/gi,"$1-webkit-user-select: unset").replace(/([\s;])-moz-user-select\s*:\s*none/gi,"$1-moz-user-select: unset").replace(/([\s;])-ms-user-select\s*:\s*none/gi,"$1-ms-user-select: unset").replace(/([\s;])-o-user-select\s*:\s*none/gi,"$1-o-user-select: unset").replace(/([\s;])user-select\s*:\s*none/gi,"$1user-select: unset").replace(/(font-family\s*:[^;]*?)\bsans-serif\b/gi,"$1MYBOOKS_SS_PLACEHOLDER").replace(/(font-family\s*:[^;]*?)\bserif\b(?!-)/gi,"$1var(--serif, serif)").replace(/MYBOOKS_SS_PLACEHOLDER/g,"var(--sans-serif, sans-serif)").replace(/(font-family\s*:[^;]*?)\bmonospace\b/gi,"$1var(--monospace, monospace)").replace(/([\s;])font-weight\s*:\s*normal/gi,"$1font-weight: var(--font-weight)").replace(/([\s;])color\s*:\s*black/gi,"$1color: var(--theme-fg-color)").replace(/([\s;])color\s*:\s*#000000/gi,"$1color: var(--theme-fg-color)").replace(/([\s;])color\s*:\s*#000/gi,"$1color: var(--theme-fg-color)").replace(/([\s;])color\s*:\s*rgb\(0,\s*0,\s*0\)/gi,"$1color: var(--theme-fg-color)");let{isDarkMode:l,bg:c}=th();return l&&(t=t.replace(o,(t,e,a)=>{let n=a.replace(/background(-color)?\s*:\s*([^;!}]+)(\s*!important)?(?=\s*[;!}])/gi,(t,e,a,n)=>(t=>{let e=t.trim().toLowerCase();if("white"===e)return!0;let a=e.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);if(a){let t=a[1],e=3===t.length?t.split("").map(t=>t+t).join(""):t;return(.299*parseInt(e.slice(0,2),16)+.587*parseInt(e.slice(2,4),16)+.114*parseInt(e.slice(4,6),16))/255>.85}let n=e.match(/^rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)$/);return n?.[1]!=null&&null!=n[2]&&null!=n[3]&&(.299*parseInt(n[1],10)+.587*parseInt(n[2],10)+.114*parseInt(n[3],10))/255>.85})(a.trim().split(/\s+/)[0]??"")?`background-color: ${c}${n??""}`:t);return n===a?t:e+n})),t}],274070)},611517,833728,t=>{"use strict";var e=t.i(460976),a=t.i(274070),n=t.i(808701),i=t.i(882209),r=t.i(243539);let o=(0,e.create)((t,e)=>{let n=localStorage&&localStorage.getItem("themeMode")||"auto",i=(()=>{if(localStorage){let t=window.__MYBOOKS_IS_EINK?"contrast":"default";return localStorage.getItem("themeColor")||t}return"default"})(),o=window.matchMedia("(prefers-color-scheme: dark)").matches;return{themeMode:n,themeColor:i,systemIsDarkMode:o,isDarkMode:"dark"===n||"auto"===n&&o,themeCode:(0,a.getThemeCode)(),systemUIVisible:!1,statusBarHeight:24,systemUIAlwaysHidden:!1,safeAreaInsets:{top:0,right:0,bottom:0,left:0},isRoundedWindow:!0,showSystemUI:()=>t({systemUIVisible:!0}),dismissSystemUI:()=>t({systemUIVisible:!1}),setStatusBarHeight:e=>t({statusBarHeight:e}),setSystemUIAlwaysHidden:e=>t({systemUIAlwaysHidden:e}),getIsDarkMode:()=>e().isDarkMode,setThemeMode:n=>{localStorage&&localStorage.setItem("themeMode",n);let i="dark"===n||"auto"===n&&e().systemIsDarkMode;document.documentElement.setAttribute("data-theme",`${e().themeColor}-${i?"dark":"light"}`),t({themeMode:n,isDarkMode:i}),t({themeCode:(0,a.getThemeCode)()})},setThemeColor:n=>{localStorage&&localStorage.setItem("themeColor",n),document.documentElement.setAttribute("data-theme",`${n}-${e().isDarkMode?"dark":"light"}`),t({themeColor:n}),t({themeCode:(0,a.getThemeCode)()})},updateAppTheme:t=>{if((0,r.isWebAppPlatform)()){let{palette:a}=e().themeCode;document.querySelector('meta[name="theme-color"]')?.setAttribute("content",a[t])}},saveCustomTheme:async(t,e,a,n)=>{let i=e.globalReadSettings.customThemes||[],r=i.findIndex(t=>t.name===a.name);n?r>-1&&i.splice(r,1):r>-1?i[r]=a:i.push(a),e.globalReadSettings.customThemes=i,localStorage.setItem("customThemes",JSON.stringify(i));let o=await t.getAppService();await o.saveSettings(e)},handleSystemThemeChange:n=>{let i=e().themeMode,r="dark"===i||"auto"===i&&n;document.documentElement.setAttribute("data-theme",`${e().themeColor}-${r?"dark":"light"}`),t({systemIsDarkMode:n,isDarkMode:r}),t({themeCode:(0,a.getThemeCode)()})},updateSafeAreaInsets:e=>{t({safeAreaInsets:e})}}});t.s(["initSystemThemeListener",0,t=>{if(!t)return;let e=window.matchMedia("(prefers-color-scheme: dark)"),a=t=>{localStorage&&localStorage.setItem("systemIsDarkMode",t?"true":"false"),o.getState().handleSystemThemeChange(t)},r=async()=>{a(t.isIOSApp?"dark"===(await (0,n.getSystemColorScheme)()).colorScheme:e.matches)},l=async()=>{if(!t.hasWindow||!t.isLinuxApp)return;let e=(0,i.getCurrentWindow)(),a=await e.isFullscreen(),n=await e.isMaximized();o.setState({isRoundedWindow:!n&&!a})};e?.addEventListener("change",r),document.addEventListener("visibilitychange",r),window.addEventListener("resize",l),t.isIOSApp&&(window.onNativeColorSchemeChange=t=>{a("dark"===t)}),r()},"loadDataTheme",0,()=>{if("u"<typeof localStorage||"u"<typeof document)return;let t=localStorage.getItem("themeMode"),e=localStorage.getItem("themeColor");if(t&&e){let a=window.matchMedia("(prefers-color-scheme: dark)").matches;document.documentElement.setAttribute("data-theme",`${e}-${"dark"===t||"auto"===t&&a?"dark":"light"}`)}},"useThemeStore",0,o],611517);var l=t.i(313547),c=t.i(810435),h=t.i(201702);t.s(["useSafeAreaInsets",0,()=>{let{appService:t}=(0,c.useEnv)(),e=(0,l.useRef)({top:0,right:0,bottom:0,left:0}),{updateSafeAreaInsets:a}=o(),i=t=>{let{top:n,right:i,bottom:r,left:o}=e.current;(t.top!==n||t.right!==i||t.bottom!==r||t.left!==o)&&(e.current=t,a(t))},r=(0,l.useCallback)(()=>{if(!t)return;if(!t.hasSafeAreaInset)return void i(e.current);let a=getComputedStyle(document.documentElement),r=a.getPropertyValue("--safe-area-inset-top");t.isIOSApp&&"macos"===(0,h.getOSPlatform)()?i({top:0,right:0,bottom:0,left:0}):t.isAndroidApp||t.isIOSApp?(0,n.getSafeAreaInsets)().then(t=>{t.error?console.error("Error getting safe area insets from native bridge:",t.error):i({top:Math.round(t.top),right:Math.round(t.right),bottom:Math.round(t.bottom),left:Math.round(t.left)})}):r&&i({top:Math.round(parseFloat(a.getPropertyValue("--safe-area-inset-top"))||0),right:Math.round(parseFloat(a.getPropertyValue("--safe-area-inset-right"))||0),bottom:Math.round(parseFloat(a.getPropertyValue("--safe-area-inset-bottom"))||0),left:Math.round(parseFloat(a.getPropertyValue("--safe-area-inset-left"))||0)})},[t]);return(0,l.useEffect)(()=>{r(),window.screen?.orientation?window.screen.orientation.addEventListener("change",r):window.addEventListener("orientationchange",r);let t=()=>{"visible"===document.visibilityState&&r()};document.addEventListener("visibilitychange",t);let e=()=>{r()};return window.addEventListener("focus",e),()=>{window.screen?.orientation?window.screen.orientation.removeEventListener("change",r):window.removeEventListener("orientationchange",r),document.removeEventListener("visibilitychange",t),window.removeEventListener("focus",e)}},[r]),{onUpdateInsets:r}}],833728)},7284,t=>{"use strict";function e(){for(var t,e,a=0,n="",i=arguments.length;a<i;a++)(t=arguments[a])&&(e=function t(e){var a,n,i="";if("string"==typeof e||"number"==typeof e)i+=e;else if("object"==typeof e)if(Array.isArray(e)){var r=e.length;for(a=0;a<r;a++)e[a]&&(n=t(e[a]))&&(i&&(i+=" "),i+=n)}else for(n in e)e[n]&&(i&&(i+=" "),i+=n);return i}(t))&&(n&&(n+=" "),n+=e);return n}t.s(["clsx",0,e,"default",0,e])},785036,t=>{"use strict";var e=t.i(940019);t.s(["MdAdd",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"},child:[]}]})(t)},"MdAlarm",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"m22 5.72-4.6-3.86-1.29 1.53 4.6 3.86L22 5.72zM7.88 3.39 6.6 1.86 2 5.71l1.29 1.53 4.59-3.85zM12.5 8H11v6l4.75 2.85.75-1.23-4-2.37V8zM12 4c-4.97 0-9 4.03-9 9s4.02 9 9 9a9 9 0 0 0 0-18zm0 16c-3.87 0-7-3.13-7-7s3.13-7 7-7 7 3.13 7 7-3.13 7-7 7z"},child:[]}]})(t)},"MdArrowBack",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z"},child:[]}]})(t)},"MdArrowBackIosNew",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M17.77 3.77 16 2 6 12l10 10 1.77-1.77L9.54 12z"},child:[]}]})(t)},"MdArrowDownward",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"m20 12-1.41-1.41L13 16.17V4h-2v12.17l-5.58-5.59L4 12l8 8 8-8z"},child:[]}]})(t)},"MdArrowDropDown",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"m7 10 5 5 5-5z"},child:[]}]})(t)},"MdArrowForwardIos",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M6.23 20.23 8 22l10-10L8 2 6.23 3.77 14.46 12z"},child:[]}]})(t)},"MdArrowUpward",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"m4 12 1.41 1.41L11 7.83V20h2V7.83l5.58 5.59L20 12l-8-8-8 8z"},child:[]}]})(t)},"MdAutoStories",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"m19 1-5 5v11l5-4.5V1zM1 6v14.65c0 .25.25.5.5.5.1 0 .15-.05.25-.05C3.1 20.45 5.05 20 6.5 20c1.95 0 4.05.4 5.5 1.5V6c-1.45-1.1-3.55-1.5-5.5-1.5S2.45 4.9 1 6zm22 13.5V6c-.6-.45-1.25-.75-2-1v13.5c-1.1-.35-2.3-.5-3.5-.5-1.7 0-4.15.65-5.5 1.5v2c1.35-.85 3.8-1.5 5.5-1.5 1.65 0 3.35.3 4.75 1.05.1.05.15.05.25.05.25 0 .5-.25.5-.5v-1.1z"},child:[]}]})(t)},"MdBook",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M18 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zM6 4h5v8l-2.5-1.5L6 12V4z"},child:[]}]})(t)},"MdBookmarkAdd",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M21 7h-2v2h-2V7h-2V5h2V3h2v2h2v2zm-2 14-7-3-7 3V5c0-1.1.9-2 2-2h7a5.002 5.002 0 0 0 5 7.9V21z"},child:[]}]})(t)},"MdBookmarkBorder",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M17 3H7c-1.1 0-1.99.9-1.99 2L5 21l7-3 7 3V5c0-1.1-.9-2-2-2zm0 15-5-2.18L7 18V5h10v13z"},child:[]}]})(t)},"MdBusiness",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 7V3H2v18h20V7H12zM6 19H4v-2h2v2zm0-4H4v-2h2v2zm0-4H4V9h2v2zm0-4H4V5h2v2zm4 12H8v-2h2v2zm0-4H8v-2h2v2zm0-4H8V9h2v2zm0-4H8V5h2v2zm10 12h-8v-2h2v-2h-2v-2h2v-2h-2V9h8v10zm-2-8h-2v2h2v-2zm0 4h-2v2h2v-2z"},child:[]}]})(t)},"MdCancel",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 2C6.47 2 2 6.47 2 12s4.47 10 10 10 10-4.47 10-10S17.53 2 12 2zm5 13.59L15.59 17 12 13.41 8.41 17 7 15.59 10.59 12 7 8.41 8.41 7 12 10.59 15.59 7 17 8.41 13.41 12 17 15.59z"},child:[]}]})(t)},"MdCategory",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"m12 2-5.5 9h11z"},child:[]},{tag:"circle",attr:{cx:"17.5",cy:"17.5",r:"4.5"},child:[]},{tag:"path",attr:{d:"M3 13.5h8v8H3z"},child:[]}]})(t)},"MdCheck",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"},child:[]}]})(t)},"MdCheckCircle",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"},child:[]}]})(t)},"MdCheckCircleOutline",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0zm0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M16.59 7.58 10 14.17l-3.59-3.58L5 12l5 5 8-8zM12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8z"},child:[]}]})(t)},"MdChecklist",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M22 7h-9v2h9V7zm0 8h-9v2h9v-2zM5.54 11 2 7.46l1.41-1.41 2.12 2.12 4.24-4.24 1.41 1.41L5.54 11zm0 8L2 15.46l1.41-1.41 2.12 2.12 4.24-4.24 1.41 1.41L5.54 19z"},child:[]}]})(t)},"MdChevronLeft",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M15.41 7.41 14 6l-6 6 6 6 1.41-1.41L10.83 12z"},child:[]}]})(t)},"MdChevronRight",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M10 6 8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z"},child:[]}]})(t)},"MdClose",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"},child:[]}]})(t)},"MdCloudDownload",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M19.35 10.04A7.49 7.49 0 0 0 12 4C9.11 4 6.6 5.64 5.35 8.04A5.994 5.994 0 0 0 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96zM17 13l-5 5-5-5h3V9h4v4h3z"},child:[]}]})(t)},"MdCloudSync",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M21.5 14.98c-.02 0-.03 0-.05.01A3.49 3.49 0 0 0 18 12c-1.4 0-2.6.83-3.16 2.02A2.988 2.988 0 0 0 12 17c0 1.66 1.34 3 3 3l6.5-.02a2.5 2.5 0 0 0 0-5zM10 4.26v2.09C7.67 7.18 6 9.39 6 12c0 1.77.78 3.34 2 4.44V14h2v6H4v-2h2.73A7.942 7.942 0 0 1 4 12c0-3.73 2.55-6.85 6-7.74zM20 6h-2.73a7.98 7.98 0 0 1 2.66 5h-2.02c-.23-1.36-.93-2.55-1.91-3.44V10h-2V4h6v2z"},child:[]}]})(t)},"MdCloudUpload",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M19.35 10.04A7.49 7.49 0 0 0 12 4C9.11 4 6.6 5.64 5.35 8.04A5.994 5.994 0 0 0 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96zM14 13v4h-4v-4H7l5-5 5 5h-3z"},child:[]}]})(t)},"MdCollectionsBookmark",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M4 6H2v14c0 1.1.9 2 2 2h14v-2H4V6z"},child:[]},{tag:"path",attr:{d:"M20 2H8c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 10-2.5-1.5L15 12V4h5v8z"},child:[]}]})(t)},"MdContentCopy",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"},child:[]}]})(t)},"MdContrast",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 22c5.52 0 10-4.48 10-10S17.52 2 12 2 2 6.48 2 12s4.48 10 10 10zm1-17.93c3.94.49 7 3.85 7 7.93s-3.05 7.44-7 7.93V4.07z"},child:[]}]})(t)},"MdDelete",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"},child:[]}]})(t)},"MdDeleteOutline",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM8 9h8v10H8V9zm7.5-5-1-1h-5l-1 1H5v2h14V4z"},child:[]}]})(t)},"MdDeleteSweep",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M15 16h4v2h-4zm0-8h7v2h-7zm0 4h6v2h-6zM3 18c0 1.1.9 2 2 2h6c1.1 0 2-.9 2-2V8H3v10zM14 5h-3l-1-1H6L5 5H2v2h12z"},child:[]}]})(t)},"MdDevices",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M4 6h18V4H4c-1.1 0-2 .9-2 2v11H0v3h14v-3H4V6zm19 2h-6c-.55 0-1 .45-1 1v10c0 .55.45 1 1 1h6c.55 0 1-.45 1-1V9c0-.55-.45-1-1-1zm-1 9h-4v-7h4v7z"},child:[]}]})(t)},"MdDownload",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M5 20h14v-2H5v2zM19 9h-4V3H9v6H5l7 7 7-7z"},child:[]}]})(t)},"MdDownloadForOffline",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 2C6.49 2 2 6.49 2 12s4.49 10 10 10 10-4.49 10-10S17.51 2 12 2zm-1 8V6h2v4h3l-4 4-4-4h3zm6 7H7v-2h10v2z"},child:[]}]})(t)},"MdDragIndicator",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M11 18c0 1.1-.9 2-2 2s-2-.9-2-2 .9-2 2-2 2 .9 2 2zm-2-8c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0-6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm6 4c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z"},child:[]}]})(t)},"MdEdit",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a.996.996 0 0 0 0-1.41l-2.34-2.34a.996.996 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"},child:[]}]})(t)},"MdError",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"},child:[]}]})(t)},"MdErrorOutline",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M11 15h2v2h-2zm0-8h2v6h-2zm.99-5C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8z"},child:[]}]})(t)},"MdExpandLess",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"m12 8-6 6 1.41 1.41L12 10.83l4.59 4.58L18 14z"},child:[]}]})(t)},"MdExpandMore",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M16.59 8.59 12 13.17 7.41 8.59 6 10l6 6 6-6z"},child:[]}]})(t)},"MdFavorite",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"m12 21.35-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"},child:[]}]})(t)},"MdFileUpload",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M9 16h6v-6h4l-7-7-7 7h4zm-4 2h14v2H5z"},child:[]}]})(t)},"MdFolder",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M10 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z"},child:[]}]})(t)},"MdFolderCopy",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M3 6H1v13c0 1.1.9 2 2 2h17v-2H3V6z"},child:[]},{tag:"path",attr:{d:"M21 4h-7l-2-2H7c-1.1 0-1.99.9-1.99 2L5 15c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2z"},child:[]}]})(t)},"MdFolderOff",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M20 6h-8l-2-2H6.83l14.93 14.93c.15-.28.24-.59.24-.93V8c0-1.1-.9-2-2-2zM2.1 2.1.69 3.51l1.56 1.56c-.15.28-.24.59-.24.93L2 18c0 1.1.9 2 2 2h13.17l3.31 3.31 1.41-1.41L2.1 2.1z"},child:[]}]})(t)},"MdFolderOpen",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M20 6h-8l-2-2H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2zm0 12H4V8h16v10z"},child:[]}]})(t)},"MdGraphicEq",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M7 18h2V6H7v12zm4 4h2V2h-2v20zm-8-8h2v-4H3v4zm12 4h2V6h-2v12zm4-8v4h2v-4h-2z"},child:[]}]})(t)},"MdHeadphones",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 3a9 9 0 0 0-9 9v7c0 1.1.9 2 2 2h4v-8H5v-1c0-3.87 3.13-7 7-7s7 3.13 7 7v1h-4v8h4c1.1 0 2-.9 2-2v-7a9 9 0 0 0-9-9z"},child:[]}]})(t)},"MdHome",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z"},child:[]}]})(t)},"MdInfoOutline",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M11 7h2v2h-2V7zm0 4h2v6h-2v-6zm1-9C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z"},child:[]}]})(t)},"MdInsertDriveFile",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M6 2c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6H6zm7 7V3.5L18.5 9H13z"},child:[]}]})(t)},"MdKeyboardArrowDown",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M7.41 8.59 12 13.17l4.59-4.58L18 10l-6 6-6-6 1.41-1.41z"},child:[]}]})(t)},"MdKeyboardArrowLeft",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M15.41 16.59 10.83 12l4.58-4.59L14 6l-6 6 6 6 1.41-1.41z"},child:[]}]})(t)},"MdKeyboardArrowRight",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M8.59 16.59 13.17 12 8.59 7.41 10 6l6 6-6 6-1.41-1.41z"},child:[]}]})(t)},"MdKeyboardArrowUp",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M7.41 15.41 12 10.83l4.59 4.58L18 14l-6-6-6 6z"},child:[]}]})(t)},"MdKeyboardDoubleArrowLeft",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M17.59 18 19 16.59 14.42 12 19 7.41 17.59 6l-6 6z"},child:[]},{tag:"path",attr:{d:"m11 18 1.41-1.41L7.83 12l4.58-4.59L11 6l-6 6z"},child:[]}]})(t)},"MdKeyboardDoubleArrowRight",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M6.41 6 5 7.41 9.58 12 5 16.59 6.41 18l6-6z"},child:[]},{tag:"path",attr:{d:"m13 6-1.41 1.41L16.17 12l-4.58 4.59L13 18l6-6z"},child:[]}]})(t)},"MdLibraryAddCheck",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M20 2H8c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-7.53 12L9 10.5l1.4-1.41 2.07 2.08L17.6 6 19 7.41 12.47 14zM4 6H2v14c0 1.1.9 2 2 2h14v-2H4V6z"},child:[]}]})(t)},"MdLink",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M3.9 12c0-1.71 1.39-3.1 3.1-3.1h4V7H7c-2.76 0-5 2.24-5 5s2.24 5 5 5h4v-1.9H7c-1.71 0-3.1-1.39-3.1-3.1zM8 13h8v-2H8v2zm9-6h-4v1.9h4c1.71 0 3.1 1.39 3.1 3.1s-1.39 3.1-3.1 3.1h-4V17h4c2.76 0 5-2.24 5-5s-2.24-5-5-5z"},child:[]}]})(t)},"MdLocalOffer",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"m21.41 11.58-9-9C12.05 2.22 11.55 2 11 2H4c-1.1 0-2 .9-2 2v7c0 .55.22 1.05.59 1.42l9 9c.36.36.86.58 1.41.58.55 0 1.05-.22 1.41-.59l7-7c.37-.36.59-.86.59-1.41 0-.55-.23-1.06-.59-1.42zM5.5 7C4.67 7 4 6.33 4 5.5S4.67 4 5.5 4 7 4.67 7 5.5 6.33 7 5.5 7z"},child:[]}]})(t)},"MdLock",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z"},child:[]}]})(t)},"MdLockOpen",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 17c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm6-9h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6h1.9c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm0 12H6V10h12v10z"},child:[]}]})(t)},"MdLogout",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"m17 7-1.41 1.41L18.17 11H8v2h10.17l-2.58 2.58L17 17l5-5zM4 5h8V3H4c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h8v-2H4V5z"},child:[]}]})(t)},"MdNightlightRound",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M12.01 12c0-3.57 2.2-6.62 5.31-7.87.89-.36.75-1.69-.19-1.9-1.1-.24-2.27-.3-3.48-.14-4.51.6-8.12 4.31-8.59 8.83C4.44 16.93 9.13 22 15.01 22c.73 0 1.43-.08 2.12-.23.95-.21 1.1-1.53.2-1.9A8.46 8.46 0 0 1 12.01 12z"},child:[]}]})(t)},"MdNoteAdd",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 14h-3v3h-2v-3H8v-2h3v-3h2v3h3v2zm-3-7V3.5L18.5 9H13z"},child:[]}]})(t)},"MdOfflinePin",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10 10-4.5 10-10S17.5 2 12 2zm5 16H7v-2h10v2zm-6.7-4L7 10.7l1.4-1.4 1.9 1.9 5.3-5.3L17 7.3 10.3 14z"},child:[]}]})(t)},"MdOpenInNew",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M19 19H5V5h7V3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14c1.1 0 2-.9 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z"},child:[]}]})(t)},"MdOutlineAutoMode",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M19.03 3.56c-1.67-1.39-3.74-2.3-6.03-2.51v2.01c1.73.19 3.31.88 4.61 1.92l1.42-1.42zM11 3.06V1.05c-2.29.2-4.36 1.12-6.03 2.51l1.42 1.42A8.928 8.928 0 0 1 11 3.06zM4.98 6.39 3.56 4.97C2.17 6.64 1.26 8.71 1.05 11h2.01c.19-1.73.88-3.31 1.92-4.61zM20.94 11h2.01c-.21-2.29-1.12-4.36-2.51-6.03l-1.42 1.42A8.928 8.928 0 0 1 20.94 11zM7 12l3.44 1.56L12 17l1.56-3.44L17 12l-3.44-1.56L12 7l-1.56 3.44z"},child:[]},{tag:"path",attr:{d:"M12 21a8.96 8.96 0 0 1-7.46-4H7v-2H1v6h2v-2.7c1.99 2.84 5.27 4.7 9 4.7 4.87 0 9-3.17 10.44-7.56l-1.96-.45C19.25 18.48 15.92 21 12 21z"},child:[]}]})(t)},"MdOutlineCancel",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z",opacity:".87"},child:[]},{tag:"path",attr:{d:"M12 2C6.47 2 2 6.47 2 12s4.47 10 10 10 10-4.47 10-10S17.53 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm3.59-13L12 10.59 8.41 7 7 8.41 10.59 12 7 15.59 8.41 17 12 13.41 15.59 17 17 15.59 13.41 12 17 8.41z"},child:[]}]})(t)},"MdOutlineCheck",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41L9 16.17z"},child:[]}]})(t)},"MdOutlineCloudDownload",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M19.35 10.04A7.49 7.49 0 0 0 12 4C9.11 4 6.6 5.64 5.35 8.04A5.994 5.994 0 0 0 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96zM19 18H6c-2.21 0-4-1.79-4-4 0-2.05 1.53-3.76 3.56-3.97l1.07-.11.5-.95A5.469 5.469 0 0 1 12 6c2.62 0 4.88 1.86 5.39 4.43l.3 1.5 1.53.11A2.98 2.98 0 0 1 22 15c0 1.65-1.35 3-3 3zm-5.55-8h-2.9v3H8l4 4 4-4h-2.55z"},child:[]}]})(t)},"MdOutlineCloudOff",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M24 15c0-2.64-2.05-4.78-4.65-4.96A7.49 7.49 0 0 0 12 4c-1.33 0-2.57.36-3.65.97l1.49 1.49C10.51 6.17 11.23 6 12 6c3.04 0 5.5 2.46 5.5 5.5v.5H19a2.996 2.996 0 0 1 1.79 5.4l1.41 1.41c1.09-.92 1.8-2.27 1.8-3.81zM4.41 3.86 3 5.27l2.77 2.77h-.42A5.994 5.994 0 0 0 0 14c0 3.31 2.69 6 6 6h11.73l2 2 1.41-1.41L4.41 3.86zM6 18c-2.21 0-4-1.79-4-4s1.79-4 4-4h1.73l8 8H6z"},child:[]}]})(t)},"MdOutlineCloudQueue",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M19.35 10.04A7.49 7.49 0 0 0 12 4C9.11 4 6.6 5.64 5.35 8.04A5.994 5.994 0 0 0 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96zM19 18H6c-2.21 0-4-1.79-4-4s1.79-4 4-4h.71C7.37 7.69 9.48 6 12 6c3.04 0 5.5 2.46 5.5 5.5v.5H19c1.66 0 3 1.34 3 3s-1.34 3-3 3z"},child:[]}]})(t)},"MdOutlineCloudUpload",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M19.35 10.04A7.49 7.49 0 0 0 12 4C9.11 4 6.6 5.64 5.35 8.04A5.994 5.994 0 0 0 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96zM19 18H6c-2.21 0-4-1.79-4-4 0-2.05 1.53-3.76 3.56-3.97l1.07-.11.5-.95A5.469 5.469 0 0 1 12 6c2.62 0 4.88 1.86 5.39 4.43l.3 1.5 1.53.11A2.98 2.98 0 0 1 22 15c0 1.65-1.35 3-3 3zM8 13h2.55v3h2.9v-3H16l-4-4z"},child:[]}]})(t)},"MdOutlineDarkMode",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M9.37 5.51A7.35 7.35 0 0 0 9.1 7.5c0 4.08 3.32 7.4 7.4 7.4.68 0 1.35-.09 1.99-.27A7.014 7.014 0 0 1 12 19c-3.86 0-7-3.14-7-7 0-2.93 1.81-5.45 4.37-6.49zM12 3a9 9 0 1 0 9 9c0-.46-.04-.92-.1-1.36a5.389 5.389 0 0 1-4.4 2.26 5.403 5.403 0 0 1-3.14-9.8c-.44-.06-.9-.1-1.36-.1z"},child:[]}]})(t)},"MdOutlineDelete",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M16 9v10H8V9h8m-1.5-6h-5l-1 1H5v2h14V4h-3.5l-1-1zM18 7H6v12c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7z"},child:[]}]})(t)},"MdOutlineDownload",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M19 9h-4V3H9v6H5l7 7 7-7zm-8 2V5h2v6h1.17L12 13.17 9.83 11H11zm-6 7h14v2H5z"},child:[]}]})(t)},"MdOutlineEdit",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"m14.06 9.02.92.92L5.92 19H5v-.92l9.06-9.06M17.66 3c-.25 0-.51.1-.7.29l-1.83 1.83 3.75 3.75 1.83-1.83a.996.996 0 0 0 0-1.41l-2.34-2.34c-.2-.2-.45-.29-.71-.29zm-3.6 3.19L3 17.25V21h3.75L17.81 9.94l-3.75-3.75z"},child:[]}]})(t)},"MdOutlineFileDownload",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M18 15v3H6v-3H4v3c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2v-3h-2zm-1-4-1.41-1.41L13 12.17V4h-2v8.17L8.41 9.59 7 11l5 5 5-5z"},child:[]}]})(t)},"MdOutlineForum",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M15 4v7H5.17L4 12.17V4h11m1-2H3c-.55 0-1 .45-1 1v14l4-4h10c.55 0 1-.45 1-1V3c0-.55-.45-1-1-1zm5 4h-2v9H6v2c0 .55.45 1 1 1h11l4 4V7c0-.55-.45-1-1-1z"},child:[]}]})(t)},"MdOutlineFullscreen",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z"},child:[]}]})(t)},"MdOutlineHeadphones",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 3a9 9 0 0 0-9 9v7c0 1.1.9 2 2 2h4v-8H5v-1c0-3.87 3.13-7 7-7s7 3.13 7 7v1h-4v8h4c1.1 0 2-.9 2-2v-7a9 9 0 0 0-9-9zM7 15v4H5v-4h2zm12 4h-2v-4h2v4z"},child:[]}]})(t)},"MdOutlineInfo",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M11 7h2v2h-2zm0 4h2v6h-2zm1-9C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z"},child:[]}]})(t)},"MdOutlineLibraryAddCheck",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{d:"M20 4v12H8V4h12m0-2H8c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-7.53 12L9 10.5l1.4-1.41 2.07 2.08L17.6 6 19 7.41 12.47 14zM4 6H2v14c0 1.1.9 2 2 2h14v-2H4V6z"},child:[]},{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]}]})(t)},"MdOutlineLightMode",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 9c1.65 0 3 1.35 3 3s-1.35 3-3 3-3-1.35-3-3 1.35-3 3-3m0-2c-2.76 0-5 2.24-5 5s2.24 5 5 5 5-2.24 5-5-2.24-5-5-5zM2 13h2c.55 0 1-.45 1-1s-.45-1-1-1H2c-.55 0-1 .45-1 1s.45 1 1 1zm18 0h2c.55 0 1-.45 1-1s-.45-1-1-1h-2c-.55 0-1 .45-1 1s.45 1 1 1zM11 2v2c0 .55.45 1 1 1s1-.45 1-1V2c0-.55-.45-1-1-1s-1 .45-1 1zm0 18v2c0 .55.45 1 1 1s1-.45 1-1v-2c0-.55-.45-1-1-1s-1 .45-1 1zM5.99 4.58a.996.996 0 0 0-1.41 0 .996.996 0 0 0 0 1.41l1.06 1.06c.39.39 1.03.39 1.41 0s.39-1.03 0-1.41L5.99 4.58zm12.37 12.37a.996.996 0 0 0-1.41 0 .996.996 0 0 0 0 1.41l1.06 1.06c.39.39 1.03.39 1.41 0a.996.996 0 0 0 0-1.41l-1.06-1.06zm1.06-10.96a.996.996 0 0 0 0-1.41.996.996 0 0 0-1.41 0l-1.06 1.06c-.39.39-.39 1.03 0 1.41s1.03.39 1.41 0l1.06-1.06zM7.05 18.36a.996.996 0 0 0 0-1.41.996.996 0 0 0-1.41 0l-1.06 1.06c-.39.39-.39 1.03 0 1.41s1.03.39 1.41 0l1.06-1.06z"},child:[]}]})(t)},"MdOutlineMenu",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M3 18h18v-2H3v2zm0-5h18v-2H3v2zm0-7v2h18V6H3z"},child:[]}]})(t)},"MdOutlineNoAccounts",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M15.18 10.94c.2-.44.32-.92.32-1.44C15.5 7.57 13.93 6 12 6c-.52 0-1 .12-1.44.32l4.62 4.62z"},child:[]},{tag:"path",attr:{d:"M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zM4 12c0-1.85.63-3.55 1.69-4.9l2.86 2.86a3.47 3.47 0 0 0 2.99 2.99l2.2 2.2c-.57-.1-1.15-.15-1.74-.15-2.32 0-4.45.8-6.14 2.12A7.957 7.957 0 0 1 4 12zm8 8c-1.74 0-3.34-.56-4.65-1.5C8.66 17.56 10.26 17 12 17s3.34.56 4.65 1.5c-1.31.94-2.91 1.5-4.65 1.5zm6.31-3.1L7.1 5.69A7.902 7.902 0 0 1 12 4c4.42 0 8 3.58 8 8 0 1.85-.63 3.54-1.69 4.9z"},child:[]}]})(t)},"MdOutlinePause",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M6 19h4V5H6v14zm8-14v14h4V5h-4z"},child:[]}]})(t)},"MdOutlinePushPin",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M14 4v5c0 1.12.37 2.16 1 3H9c.65-.86 1-1.9 1-3V4h4m3-2H7c-.55 0-1 .45-1 1s.45 1 1 1h1v5c0 1.66-1.34 3-3 3v2h5.97v7l1 1 1-1v-7H19v-2c-1.66 0-3-1.34-3-3V4h1c.55 0 1-.45 1-1s-.45-1-1-1z"},child:[]}]})(t)},"MdOutlineRestartAlt",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M6 13c0-1.65.67-3.15 1.76-4.24L6.34 7.34A8.014 8.014 0 0 0 4 13c0 4.08 3.05 7.44 7 7.93v-2.02c-2.83-.48-5-2.94-5-5.91zm14 0c0-4.42-3.58-8-8-8-.06 0-.12.01-.18.01l1.09-1.09L11.5 2.5 8 6l3.5 3.5 1.41-1.41-1.08-1.08c.06 0 .12-.01.17-.01 3.31 0 6 2.69 6 6 0 2.97-2.17 5.43-5 5.91v2.02c3.95-.49 7-3.85 7-7.93z"},child:[]}]})(t)},"MdOutlineScreenRotation",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M16.48 2.52c3.27 1.55 5.61 4.72 5.97 8.48h1.5C23.44 4.84 18.29 0 12 0l-.66.03 3.81 3.81 1.33-1.32zm-6.25-.77a1.49 1.49 0 0 0-2.12 0L1.75 8.11a1.49 1.49 0 0 0 0 2.12l12.02 12.02c.59.59 1.54.59 2.12 0l6.36-6.36c.59-.59.59-1.54 0-2.12L10.23 1.75zm4.6 19.44L2.81 9.17l6.36-6.36 12.02 12.02-6.36 6.36zm-7.31.29A10.487 10.487 0 0 1 1.55 13H.05C.56 19.16 5.71 24 12 24l.66-.03-3.81-3.81-1.33 1.32z"},child:[]}]})(t)},"MdOutlineTextRotationNone",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"m21 18-3-3v2H5v2h13v2l3-3zM9.5 11.8h5l.9 2.2h2.1L12.75 3h-1.5L6.5 14h2.1l.9-2.2zM12 4.98 13.87 10h-3.74L12 4.98z"},child:[]}]})(t)},"MdOutlineThumbUpOffAlt",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M9 21h9c.83 0 1.54-.5 1.84-1.22l3.02-7.05c.09-.23.14-.47.14-.73v-2c0-1.1-.9-2-2-2h-6.31l.95-4.57.03-.32c0-.41-.17-.79-.44-1.06L14.17 1 7.58 7.59C7.22 7.95 7 8.45 7 9v10c0 1.1.9 2 2 2zM9 9l4.34-4.34L12 10h9v2l-3 7H9V9zM1 9h4v12H1V9z"},child:[]}]})(t)},"MdPause",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M6 19h4V5H6v14zm8-14v14h4V5h-4z"},child:[]}]})(t)},"MdPauseCircleFilled",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 14H9V8h2v8zm4 0h-2V8h2v8z"},child:[]}]})(t)},"MdPeople",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z"},child:[]}]})(t)},"MdPersonOutline",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 5.9a2.1 2.1 0 1 1 0 4.2 2.1 2.1 0 0 1 0-4.2m0 9c2.97 0 6.1 1.46 6.1 2.1v1.1H5.9V17c0-.64 3.13-2.1 6.1-2.1M12 4C9.79 4 8 5.79 8 8s1.79 4 4 4 4-1.79 4-4-1.79-4-4-4zm0 9c-2.67 0-8 1.34-8 4v3h16v-3c0-2.66-5.33-4-8-4z"},child:[]}]})(t)},"MdPhoneAndroid",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M16 1H8C6.34 1 5 2.34 5 4v16c0 1.66 1.34 3 3 3h8c1.66 0 3-1.34 3-3V4c0-1.66-1.34-3-3-3zm-2 20h-4v-1h4v1zm3.25-3H6.75V4h10.5v14z"},child:[]}]})(t)},"MdPlayArrow",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M8 5v14l11-7z"},child:[]}]})(t)},"MdPlayCircleFilled",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 14.5v-9l6 4.5-6 4.5z"},child:[]}]})(t)},"MdPlayCircleOutline",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"m10 16.5 6-4.5-6-4.5v9zM12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z"},child:[]}]})(t)},"MdPushPin",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{fillRule:"evenodd",d:"M16 9V4h1c.55 0 1-.45 1-1s-.45-1-1-1H7c-.55 0-1 .45-1 1s.45 1 1 1h1v5c0 1.66-1.34 3-3 3v2h5.97v7l1 1 1-1v-7H19v-2c-1.66 0-3-1.34-3-3z"},child:[]}]})(t)},"MdRadioButtonChecked",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 7c-2.76 0-5 2.24-5 5s2.24 5 5 5 5-2.24 5-5-2.24-5-5-5zm0-5C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8z"},child:[]}]})(t)},"MdRadioButtonUnchecked",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8z"},child:[]}]})(t)},"MdRefresh",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M17.65 6.35A7.958 7.958 0 0 0 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08A5.99 5.99 0 0 1 12 18c-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"},child:[]}]})(t)},"MdRemove",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M19 13H5v-2h14v2z"},child:[]}]})(t)},"MdRssFeed",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"circle",attr:{cx:"6.18",cy:"17.82",r:"2.18"},child:[]},{tag:"path",attr:{d:"M4 4.44v2.83c7.03 0 12.73 5.7 12.73 12.73h2.83c0-8.59-6.97-15.56-15.56-15.56zm0 5.66v2.83c3.9 0 7.07 3.17 7.07 7.07h2.83c0-5.47-4.43-9.9-9.9-9.9z"},child:[]}]})(t)},"MdSaveAlt",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M19 12v7H5v-7H3v7c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2v-7h-2zm-6 .67 2.59-2.58L17 11.5l-5 5-5-5 1.41-1.41L11 12.67V3h2z"},child:[]}]})(t)},"MdSearch",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"},child:[]}]})(t)},"MdSettings",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.488.488 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"},child:[]}]})(t)},"MdShield",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 1 3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4z"},child:[]}]})(t)},"MdSkipNext",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"m6 18 8.5-6L6 6v12zM16 6v12h2V6h-2z"},child:[]}]})(t)},"MdSkipPrevious",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M6 6h2v12H6zm3.5 6 8.5 6V6z"},child:[]}]})(t)},"MdSpeed",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"m20.38 8.57-1.23 1.85a8 8 0 0 1-.22 7.58H5.07A8 8 0 0 1 15.58 6.85l1.85-1.23A10 10 0 0 0 3.35 19a2 2 0 0 0 1.72 1h13.85a2 2 0 0 0 1.74-1 10 10 0 0 0-.27-10.44zm-9.79 6.84a2 2 0 0 0 2.83 0l5.66-8.49-8.49 5.66a2 2 0 0 0 0 2.83z"},child:[]}]})(t)},"MdStar",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 17.27 18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"},child:[]}]})(t)},"MdStarBorder",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"m22 9.24-7.19-.62L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21 12 17.27 18.18 21l-1.63-7.03L22 9.24zM12 15.4l-3.76 2.27 1-4.28-3.32-2.88 4.38-.38L12 6.1l1.71 4.04 4.38.38-3.32 2.88 1 4.28L12 15.4z"},child:[]}]})(t)},"MdStop",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M6 6h12v12H6z"},child:[]}]})(t)},"MdSync",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46A7.93 7.93 0 0 0 20 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74A7.93 7.93 0 0 0 4 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z"},child:[]}]})(t)},"MdSyncProblem",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M3 12c0 2.21.91 4.2 2.36 5.64L3 20h6v-6l-2.24 2.24A6.003 6.003 0 0 1 5 12a5.99 5.99 0 0 1 4-5.65V4.26C5.55 5.15 3 8.27 3 12zm8 5h2v-2h-2v2zM21 4h-6v6l2.24-2.24A6.003 6.003 0 0 1 19 12a5.99 5.99 0 0 1-4 5.65v2.09c3.45-.89 6-4.01 6-7.74 0-2.21-.91-4.2-2.36-5.64L21 4zm-10 9h2V7h-2v6z"},child:[]}]})(t)},"MdTextRotateVertical",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M15.75 5h-1.5L9.5 16h2.1l.9-2.2h5l.9 2.2h2.1L15.75 5zm-2.62 7L15 6.98 16.87 12h-3.74zM6 19.75l3-3H7V4.25H5v12.5H3l3 3z"},child:[]}]})(t)},"MdTranslate",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"m12.87 15.07-2.54-2.51.03-.03A17.52 17.52 0 0 0 14.07 6H17V4h-7V2H8v2H1v1.99h11.17C11.5 7.92 10.44 9.75 9 11.35 8.07 10.32 7.3 9.19 6.69 8h-2c.73 1.63 1.73 3.17 2.98 4.56l-5.09 5.02L4 19l5-5 3.11 3.11.76-2.04zM18.5 10h-2L12 22h2l1.12-3h4.75L21 22h2l-4.5-12zm-2.62 7 1.62-4.33L19.12 17h-3.24z"},child:[]}]})(t)},"MdVisibility",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"},child:[]}]})(t)},"MdVisibilityOff",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0zm0 0h24v24H0zm0 0h24v24H0zm0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 7c2.76 0 5 2.24 5 5 0 .65-.13 1.26-.36 1.83l2.92 2.92c1.51-1.26 2.7-2.89 3.43-4.75-1.73-4.39-6-7.5-11-7.5-1.4 0-2.74.25-3.98.7l2.16 2.16C10.74 7.13 11.35 7 12 7zM2 4.27l2.28 2.28.46.46A11.804 11.804 0 0 0 1 12c1.73 4.39 6 7.5 11 7.5 1.55 0 3.03-.3 4.38-.84l.42.42L19.73 22 21 20.73 3.27 3 2 4.27zM7.53 9.8l1.55 1.55c-.05.21-.08.43-.08.65 0 1.66 1.34 3 3 3 .22 0 .44-.03.65-.08l1.55 1.55c-.67.33-1.41.53-2.2.53-2.76 0-5-2.24-5-5 0-.79.2-1.53.53-2.2zm4.31-.78 3.15 3.15.02-.16c0-1.66-1.34-3-3-3l-.17.01z"},child:[]}]})(t)},"MdVolumeUp",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M3 9v6h4l5 5V4L7 9H3zm13.5 3A4.5 4.5 0 0 0 14 7.97v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"},child:[]}]})(t)},"MdZoomIn",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"},child:[]},{tag:"path",attr:{d:"M12 10h-2v2H9v-2H7V9h2V7h1v2h2v1z"},child:[]}]})(t)},"MdZoomOut",0,function(t){return(0,e.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14zM7 9h5v1H7z"},child:[]}]})(t)}])},131989,684123,t=>{"use strict";var e,a,n=t.i(594896),i=t.i(199417),r=t.i(991024),o=t.i(882209);function l(){return new s((0,o.getCurrentWindow)(),window.__TAURI_INTERNALS__.metadata.currentWebview.label,{skip:!0})}async function c(){return(0,r.invoke)("plugin:webview|get_all_webviews").then(t=>t.map(t=>new s(new o.Window(t.windowLabel,{skip:!0}),t.label,{skip:!0})))}let h=["tauri://created","tauri://error"];class s{constructor(t,e,a){this.window=t,this.label=e,this.listeners=Object.create(null),(null==a?void 0:a.skip)||(0,r.invoke)("plugin:webview|create_webview",{windowLabel:t.label,options:{...a,label:e}}).then(async()=>this.emit("tauri://created")).catch(async t=>this.emit("tauri://error",t))}static async getByLabel(t){var e;return null!=(e=(await c()).find(e=>e.label===t))?e:null}static getCurrent(){return l()}static async getAll(){return c()}async listen(t,e){return this._handleTauriEvent(t,e)?()=>{let a=this.listeners[t];a.splice(a.indexOf(e),1)}:(0,i.listen)(t,e,{target:{kind:"Webview",label:this.label}})}async once(t,e){return this._handleTauriEvent(t,e)?()=>{let a=this.listeners[t];a.splice(a.indexOf(e),1)}:(0,i.once)(t,e,{target:{kind:"Webview",label:this.label}})}async emit(t,e){if(h.includes(t)){for(let a of this.listeners[t]||[])a({event:t,id:-1,payload:e});return}return(0,i.emit)(t,e)}async emitTo(t,e,a){if(h.includes(e)){for(let t of this.listeners[e]||[])t({event:e,id:-1,payload:a});return}return(0,i.emitTo)(t,e,a)}_handleTauriEvent(t,e){return!!h.includes(t)&&(t in this.listeners?this.listeners[t].push(e):this.listeners[t]=[e],!0)}async position(){return(0,r.invoke)("plugin:webview|webview_position",{label:this.label}).then(t=>new n.PhysicalPosition(t))}async size(){return(0,r.invoke)("plugin:webview|webview_size",{label:this.label}).then(t=>new n.PhysicalSize(t))}async close(){return(0,r.invoke)("plugin:webview|webview_close",{label:this.label})}async setSize(t){return(0,r.invoke)("plugin:webview|set_webview_size",{label:this.label,value:t instanceof n.Size?t:new n.Size(t)})}async setPosition(t){return(0,r.invoke)("plugin:webview|set_webview_position",{label:this.label,value:t instanceof n.Position?t:new n.Position(t)})}async setFocus(){return(0,r.invoke)("plugin:webview|set_webview_focus",{label:this.label})}async setAutoResize(t){return(0,r.invoke)("plugin:webview|set_webview_auto_resize",{label:this.label,value:t})}async hide(){return(0,r.invoke)("plugin:webview|webview_hide",{label:this.label})}async show(){return(0,r.invoke)("plugin:webview|webview_show",{label:this.label})}async setZoom(t){return(0,r.invoke)("plugin:webview|set_webview_zoom",{label:this.label,value:t})}async reparent(t){return(0,r.invoke)("plugin:webview|reparent",{label:this.label,window:"string"==typeof t?t:t.label})}async clearAllBrowsingData(){return(0,r.invoke)("plugin:webview|clear_all_browsing_data")}async setBackgroundColor(t){return(0,r.invoke)("plugin:webview|set_webview_background_color",{color:t})}async onDragDropEvent(t){let e=await this.listen(i.TauriEvent.DRAG_ENTER,e=>{t({...e,payload:{type:"enter",paths:e.payload.paths,position:new n.PhysicalPosition(e.payload.position)}})}),a=await this.listen(i.TauriEvent.DRAG_OVER,e=>{t({...e,payload:{type:"over",position:new n.PhysicalPosition(e.payload.position)}})}),r=await this.listen(i.TauriEvent.DRAG_DROP,e=>{t({...e,payload:{type:"drop",paths:e.payload.paths,position:new n.PhysicalPosition(e.payload.position)}})}),o=await this.listen(i.TauriEvent.DRAG_LEAVE,e=>{t({...e,payload:{type:"leave"}})});return()=>{e(),r(),a(),o()}}}async function d(){return(0,r.invoke)("plugin:window|get_all_windows").then(t=>t.map(t=>new g(t,{skip:!0})))}t.s(["Webview",0,s,"getCurrentWebview",0,l],684123);class g{constructor(t,e={}){var a;this.label=t,this.listeners=Object.create(null),(null==e?void 0:e.skip)||(0,r.invoke)("plugin:webview|create_webview_window",{options:{...e,parent:"string"==typeof e.parent?e.parent:null==(a=e.parent)?void 0:a.label,label:t}}).then(async()=>this.emit("tauri://created")).catch(async t=>this.emit("tauri://error",t))}static async getByLabel(t){var e;let a=null!=(e=(await d()).find(e=>e.label===t))?e:null;return a?new g(a.label,{skip:!0}):null}static getCurrent(){return new g(l().label,{skip:!0})}static async getAll(){return d()}async listen(t,e){return this._handleTauriEvent(t,e)?()=>{let a=this.listeners[t];a.splice(a.indexOf(e),1)}:(0,i.listen)(t,e,{target:{kind:"WebviewWindow",label:this.label}})}async once(t,e){return this._handleTauriEvent(t,e)?()=>{let a=this.listeners[t];a.splice(a.indexOf(e),1)}:(0,i.once)(t,e,{target:{kind:"WebviewWindow",label:this.label}})}async setBackgroundColor(t){return(0,r.invoke)("plugin:window|set_background_color",{color:t}).then(()=>(0,r.invoke)("plugin:webview|set_webview_background_color",{color:t}))}}e=g,(Array.isArray(a=[o.Window,s])?a:[a]).forEach(t=>{Object.getOwnPropertyNames(t.prototype).forEach(a=>{var n;"object"==typeof e.prototype&&e.prototype&&a in e.prototype||Object.defineProperty(e.prototype,a,null!=(n=Object.getOwnPropertyDescriptor(t.prototype,a))?n:Object.create(null))})}),t.s(["WebviewWindow",0,g],131989)}]);