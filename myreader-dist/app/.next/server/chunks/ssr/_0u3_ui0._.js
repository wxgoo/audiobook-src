module.exports=[436676,304830,868949,851959,a=>{"use strict";var b,c,d,e=a.i(624445);function f(a){return(f="function"==typeof Symbol&&"symbol"==typeof Symbol.iterator?function(a){return typeof a}:function(a){return a&&"function"==typeof Symbol&&a.constructor===Symbol&&a!==Symbol.prototype?"symbol":typeof a})(a)}var g=/^\s+/,h=/\s+$/;function i(a,b){if(b=b||{},(a=a||"")instanceof i)return a;if(!(this instanceof i))return new i(a,b);var c,d,e,j,k,l,m,n,o,p,q,r,s,t,u,v,w,x,y,A,D=(d={r:0,g:0,b:0},e=1,j=null,k=null,l=null,m=!1,n=!1,"string"==typeof(c=a)&&(c=function(a){a=a.replace(g,"").replace(h,"").toLowerCase();var b,c=!1;if(z[a])a=z[a],c=!0;else if("transparent"==a)return{r:0,g:0,b:0,a:0,format:"name"};return(b=I.rgb.exec(a))?{r:b[1],g:b[2],b:b[3]}:(b=I.rgba.exec(a))?{r:b[1],g:b[2],b:b[3],a:b[4]}:(b=I.hsl.exec(a))?{h:b[1],s:b[2],l:b[3]}:(b=I.hsla.exec(a))?{h:b[1],s:b[2],l:b[3],a:b[4]}:(b=I.hsv.exec(a))?{h:b[1],s:b[2],v:b[3]}:(b=I.hsva.exec(a))?{h:b[1],s:b[2],v:b[3],a:b[4]}:(b=I.hex8.exec(a))?{r:E(b[1]),g:E(b[2]),b:E(b[3]),a:E(b[4])/255,format:c?"name":"hex8"}:(b=I.hex6.exec(a))?{r:E(b[1]),g:E(b[2]),b:E(b[3]),format:c?"name":"hex"}:(b=I.hex4.exec(a))?{r:E(b[1]+""+b[1]),g:E(b[2]+""+b[2]),b:E(b[3]+""+b[3]),a:E(b[4]+""+b[4])/255,format:c?"name":"hex8"}:!!(b=I.hex3.exec(a))&&{r:E(b[1]+""+b[1]),g:E(b[2]+""+b[2]),b:E(b[3]+""+b[3]),format:c?"name":"hex"}}(c)),"object"==f(c)&&(J(c.r)&&J(c.g)&&J(c.b)?(o=c.r,p=c.g,q=c.b,d={r:255*C(o,255),g:255*C(p,255),b:255*C(q,255)},m=!0,n="%"===String(c.r).substr(-1)?"prgb":"rgb"):J(c.h)&&J(c.s)&&J(c.v)?(j=G(c.s),k=G(c.v),r=c.h,s=j,t=k,r=6*C(r,360),s=C(s,100),t=C(t,100),u=Math.floor(r),v=r-u,w=t*(1-s),x=t*(1-v*s),y=t*(1-(1-v)*s),d={r:255*[t,x,w,w,y,t][A=u%6],g:255*[y,t,t,x,w,w][A],b:255*[w,w,y,t,t,x][A]},m=!0,n="hsv"):J(c.h)&&J(c.s)&&J(c.l)&&(j=G(c.s),l=G(c.l),d=function(a,b,c){var d,e,f;function g(a,b,c){return(c<0&&(c+=1),c>1&&(c-=1),c<1/6)?a+(b-a)*6*c:c<.5?b:c<2/3?a+(b-a)*(2/3-c)*6:a}if(a=C(a,360),b=C(b,100),c=C(c,100),0===b)d=e=f=c;else{var h=c<.5?c*(1+b):c+b-c*b,i=2*c-h;d=g(i,h,a+1/3),e=g(i,h,a),f=g(i,h,a-1/3)}return{r:255*d,g:255*e,b:255*f}}(c.h,j,l),m=!0,n="hsl"),c.hasOwnProperty("a")&&(e=c.a)),e=B(e),{ok:m,format:c.format||n,r:Math.min(255,Math.max(d.r,0)),g:Math.min(255,Math.max(d.g,0)),b:Math.min(255,Math.max(d.b,0)),a:e});this._originalInput=a,this._r=D.r,this._g=D.g,this._b=D.b,this._a=D.a,this._roundA=Math.round(100*this._a)/100,this._format=b.format||D.format,this._gradientType=b.gradientType,this._r<1&&(this._r=Math.round(this._r)),this._g<1&&(this._g=Math.round(this._g)),this._b<1&&(this._b=Math.round(this._b)),this._ok=D.ok}function j(a,b,c){a=C(a,255);var d,e,f=Math.max(a,b=C(b,255),c=C(c,255)),g=Math.min(a,b,c),h=(f+g)/2;if(f==g)d=e=0;else{var i=f-g;switch(e=h>.5?i/(2-f-g):i/(f+g),f){case a:d=(b-c)/i+6*(b<c);break;case b:d=(c-a)/i+2;break;case c:d=(a-b)/i+4}d/=6}return{h:d,s:e,l:h}}function k(a,b,c){a=C(a,255);var d,e=Math.max(a,b=C(b,255),c=C(c,255)),f=Math.min(a,b,c),g=e-f;if(e==f)d=0;else{switch(e){case a:d=(b-c)/g+6*(b<c);break;case b:d=(c-a)/g+2;break;case c:d=(a-b)/g+4}d/=6}return{h:d,s:0===e?0:g/e,v:e}}function l(a,b,c,d){var e=[F(Math.round(a).toString(16)),F(Math.round(b).toString(16)),F(Math.round(c).toString(16))];return d&&e[0].charAt(0)==e[0].charAt(1)&&e[1].charAt(0)==e[1].charAt(1)&&e[2].charAt(0)==e[2].charAt(1)?e[0].charAt(0)+e[1].charAt(0)+e[2].charAt(0):e.join("")}function m(a,b,c,d){return[F(H(d)),F(Math.round(a).toString(16)),F(Math.round(b).toString(16)),F(Math.round(c).toString(16))].join("")}function n(a,b){b=0===b?0:b||10;var c=i(a).toHsl();return c.s-=b/100,c.s=D(c.s),i(c)}function o(a,b){b=0===b?0:b||10;var c=i(a).toHsl();return c.s+=b/100,c.s=D(c.s),i(c)}function p(a){return i(a).desaturate(100)}function q(a,b){b=0===b?0:b||10;var c=i(a).toHsl();return c.l+=b/100,c.l=D(c.l),i(c)}function r(a,b){b=0===b?0:b||10;var c=i(a).toRgb();return c.r=Math.max(0,Math.min(255,c.r-Math.round(-(b/100*255)))),c.g=Math.max(0,Math.min(255,c.g-Math.round(-(b/100*255)))),c.b=Math.max(0,Math.min(255,c.b-Math.round(-(b/100*255)))),i(c)}function s(a,b){b=0===b?0:b||10;var c=i(a).toHsl();return c.l-=b/100,c.l=D(c.l),i(c)}function t(a,b){var c=i(a).toHsl(),d=(c.h+b)%360;return c.h=d<0?360+d:d,i(c)}function u(a){var b=i(a).toHsl();return b.h=(b.h+180)%360,i(b)}function v(a,b){if(isNaN(b)||b<=0)throw Error("Argument to polyad must be a positive number");for(var c=i(a).toHsl(),d=[i(a)],e=360/b,f=1;f<b;f++)d.push(i({h:(c.h+f*e)%360,s:c.s,l:c.l}));return d}function w(a){var b=i(a).toHsl(),c=b.h;return[i(a),i({h:(c+72)%360,s:b.s,l:b.l}),i({h:(c+216)%360,s:b.s,l:b.l})]}function x(a,b,c){b=b||6,c=c||30;var d=i(a).toHsl(),e=360/c,f=[i(a)];for(d.h=(d.h-(e*b>>1)+720)%360;--b;)d.h=(d.h+e)%360,f.push(i(d));return f}function y(a,b){b=b||6;for(var c=i(a).toHsv(),d=c.h,e=c.s,f=c.v,g=[],h=1/b;b--;)g.push(i({h:d,s:e,v:f})),f=(f+h)%1;return g}i.prototype={isDark:function(){return 128>this.getBrightness()},isLight:function(){return!this.isDark()},isValid:function(){return this._ok},getOriginalInput:function(){return this._originalInput},getFormat:function(){return this._format},getAlpha:function(){return this._a},getBrightness:function(){var a=this.toRgb();return(299*a.r+587*a.g+114*a.b)/1e3},getLuminance:function(){var a,b,c,d=this.toRgb();return a=d.r/255,b=d.g/255,.2126*(a<=.03928?a/12.92:Math.pow((a+.055)/1.055,2.4))+.7152*(b<=.03928?b/12.92:Math.pow((b+.055)/1.055,2.4))+.0722*((c=d.b/255)<=.03928?c/12.92:Math.pow((c+.055)/1.055,2.4))},setAlpha:function(a){return this._a=B(a),this._roundA=Math.round(100*this._a)/100,this},toHsv:function(){var a=k(this._r,this._g,this._b);return{h:360*a.h,s:a.s,v:a.v,a:this._a}},toHsvString:function(){var a=k(this._r,this._g,this._b),b=Math.round(360*a.h),c=Math.round(100*a.s),d=Math.round(100*a.v);return 1==this._a?"hsv("+b+", "+c+"%, "+d+"%)":"hsva("+b+", "+c+"%, "+d+"%, "+this._roundA+")"},toHsl:function(){var a=j(this._r,this._g,this._b);return{h:360*a.h,s:a.s,l:a.l,a:this._a}},toHslString:function(){var a=j(this._r,this._g,this._b),b=Math.round(360*a.h),c=Math.round(100*a.s),d=Math.round(100*a.l);return 1==this._a?"hsl("+b+", "+c+"%, "+d+"%)":"hsla("+b+", "+c+"%, "+d+"%, "+this._roundA+")"},toHex:function(a){return l(this._r,this._g,this._b,a)},toHexString:function(a){return"#"+this.toHex(a)},toHex8:function(a){var b,c,d,e,f,g;return b=this._r,c=this._g,d=this._b,e=this._a,f=a,g=[F(Math.round(b).toString(16)),F(Math.round(c).toString(16)),F(Math.round(d).toString(16)),F(H(e))],f&&g[0].charAt(0)==g[0].charAt(1)&&g[1].charAt(0)==g[1].charAt(1)&&g[2].charAt(0)==g[2].charAt(1)&&g[3].charAt(0)==g[3].charAt(1)?g[0].charAt(0)+g[1].charAt(0)+g[2].charAt(0)+g[3].charAt(0):g.join("")},toHex8String:function(a){return"#"+this.toHex8(a)},toRgb:function(){return{r:Math.round(this._r),g:Math.round(this._g),b:Math.round(this._b),a:this._a}},toRgbString:function(){return 1==this._a?"rgb("+Math.round(this._r)+", "+Math.round(this._g)+", "+Math.round(this._b)+")":"rgba("+Math.round(this._r)+", "+Math.round(this._g)+", "+Math.round(this._b)+", "+this._roundA+")"},toPercentageRgb:function(){return{r:Math.round(100*C(this._r,255))+"%",g:Math.round(100*C(this._g,255))+"%",b:Math.round(100*C(this._b,255))+"%",a:this._a}},toPercentageRgbString:function(){return 1==this._a?"rgb("+Math.round(100*C(this._r,255))+"%, "+Math.round(100*C(this._g,255))+"%, "+Math.round(100*C(this._b,255))+"%)":"rgba("+Math.round(100*C(this._r,255))+"%, "+Math.round(100*C(this._g,255))+"%, "+Math.round(100*C(this._b,255))+"%, "+this._roundA+")"},toName:function(){return 0===this._a?"transparent":!(this._a<1)&&(A[l(this._r,this._g,this._b,!0)]||!1)},toFilter:function(a){var b="#"+m(this._r,this._g,this._b,this._a),c=b,d=this._gradientType?"GradientType = 1, ":"";if(a){var e=i(a);c="#"+m(e._r,e._g,e._b,e._a)}return"progid:DXImageTransform.Microsoft.gradient("+d+"startColorstr="+b+",endColorstr="+c+")"},toString:function(a){var b=!!a;a=a||this._format;var c=!1,d=this._a<1&&this._a>=0;return!b&&d&&("hex"===a||"hex6"===a||"hex3"===a||"hex4"===a||"hex8"===a||"name"===a)?"name"===a&&0===this._a?this.toName():this.toRgbString():("rgb"===a&&(c=this.toRgbString()),"prgb"===a&&(c=this.toPercentageRgbString()),("hex"===a||"hex6"===a)&&(c=this.toHexString()),"hex3"===a&&(c=this.toHexString(!0)),"hex4"===a&&(c=this.toHex8String(!0)),"hex8"===a&&(c=this.toHex8String()),"name"===a&&(c=this.toName()),"hsl"===a&&(c=this.toHslString()),"hsv"===a&&(c=this.toHsvString()),c||this.toHexString())},clone:function(){return i(this.toString())},_applyModification:function(a,b){var c=a.apply(null,[this].concat([].slice.call(b)));return this._r=c._r,this._g=c._g,this._b=c._b,this.setAlpha(c._a),this},lighten:function(){return this._applyModification(q,arguments)},brighten:function(){return this._applyModification(r,arguments)},darken:function(){return this._applyModification(s,arguments)},desaturate:function(){return this._applyModification(n,arguments)},saturate:function(){return this._applyModification(o,arguments)},greyscale:function(){return this._applyModification(p,arguments)},spin:function(){return this._applyModification(t,arguments)},_applyCombination:function(a,b){return a.apply(null,[this].concat([].slice.call(b)))},analogous:function(){return this._applyCombination(x,arguments)},complement:function(){return this._applyCombination(u,arguments)},monochromatic:function(){return this._applyCombination(y,arguments)},splitcomplement:function(){return this._applyCombination(w,arguments)},triad:function(){return this._applyCombination(v,[3])},tetrad:function(){return this._applyCombination(v,[4])}},i.fromRatio=function(a,b){if("object"==f(a)){var c={};for(var d in a)a.hasOwnProperty(d)&&("a"===d?c[d]=a[d]:c[d]=G(a[d]));a=c}return i(a,b)},i.equals=function(a,b){return!!a&&!!b&&i(a).toRgbString()==i(b).toRgbString()},i.random=function(){return i.fromRatio({r:Math.random(),g:Math.random(),b:Math.random()})},i.mix=function(a,b,c){c=0===c?0:c||50;var d=i(a).toRgb(),e=i(b).toRgb(),f=c/100;return i({r:(e.r-d.r)*f+d.r,g:(e.g-d.g)*f+d.g,b:(e.b-d.b)*f+d.b,a:(e.a-d.a)*f+d.a})},i.readability=function(a,b){var c=i(a),d=i(b);return(Math.max(c.getLuminance(),d.getLuminance())+.05)/(Math.min(c.getLuminance(),d.getLuminance())+.05)},i.isReadable=function(a,b,c){var d,e,f,g,h,j=i.readability(a,b);switch(h=!1,(e=((d=(d=c)||{level:"AA",size:"small"}).level||"AA").toUpperCase(),f=(d.size||"small").toLowerCase(),"AA"!==e&&"AAA"!==e&&(e="AA"),"small"!==f&&"large"!==f&&(f="small"),g={level:e,size:f}).level+g.size){case"AAsmall":case"AAAlarge":h=j>=4.5;break;case"AAlarge":h=j>=3;break;case"AAAsmall":h=j>=7}return h},i.mostReadable=function(a,b,c){var d,e,f,g,h=null,j=0;e=(c=c||{}).includeFallbackColors,f=c.level,g=c.size;for(var k=0;k<b.length;k++)(d=i.readability(a,b[k]))>j&&(j=d,h=i(b[k]));return i.isReadable(a,h,{level:f,size:g})||!e?h:(c.includeFallbackColors=!1,i.mostReadable(a,["#fff","#000"],c))};var z=i.names={aliceblue:"f0f8ff",antiquewhite:"faebd7",aqua:"0ff",aquamarine:"7fffd4",azure:"f0ffff",beige:"f5f5dc",bisque:"ffe4c4",black:"000",blanchedalmond:"ffebcd",blue:"00f",blueviolet:"8a2be2",brown:"a52a2a",burlywood:"deb887",burntsienna:"ea7e5d",cadetblue:"5f9ea0",chartreuse:"7fff00",chocolate:"d2691e",coral:"ff7f50",cornflowerblue:"6495ed",cornsilk:"fff8dc",crimson:"dc143c",cyan:"0ff",darkblue:"00008b",darkcyan:"008b8b",darkgoldenrod:"b8860b",darkgray:"a9a9a9",darkgreen:"006400",darkgrey:"a9a9a9",darkkhaki:"bdb76b",darkmagenta:"8b008b",darkolivegreen:"556b2f",darkorange:"ff8c00",darkorchid:"9932cc",darkred:"8b0000",darksalmon:"e9967a",darkseagreen:"8fbc8f",darkslateblue:"483d8b",darkslategray:"2f4f4f",darkslategrey:"2f4f4f",darkturquoise:"00ced1",darkviolet:"9400d3",deeppink:"ff1493",deepskyblue:"00bfff",dimgray:"696969",dimgrey:"696969",dodgerblue:"1e90ff",firebrick:"b22222",floralwhite:"fffaf0",forestgreen:"228b22",fuchsia:"f0f",gainsboro:"dcdcdc",ghostwhite:"f8f8ff",gold:"ffd700",goldenrod:"daa520",gray:"808080",green:"008000",greenyellow:"adff2f",grey:"808080",honeydew:"f0fff0",hotpink:"ff69b4",indianred:"cd5c5c",indigo:"4b0082",ivory:"fffff0",khaki:"f0e68c",lavender:"e6e6fa",lavenderblush:"fff0f5",lawngreen:"7cfc00",lemonchiffon:"fffacd",lightblue:"add8e6",lightcoral:"f08080",lightcyan:"e0ffff",lightgoldenrodyellow:"fafad2",lightgray:"d3d3d3",lightgreen:"90ee90",lightgrey:"d3d3d3",lightpink:"ffb6c1",lightsalmon:"ffa07a",lightseagreen:"20b2aa",lightskyblue:"87cefa",lightslategray:"789",lightslategrey:"789",lightsteelblue:"b0c4de",lightyellow:"ffffe0",lime:"0f0",limegreen:"32cd32",linen:"faf0e6",magenta:"f0f",maroon:"800000",mediumaquamarine:"66cdaa",mediumblue:"0000cd",mediumorchid:"ba55d3",mediumpurple:"9370db",mediumseagreen:"3cb371",mediumslateblue:"7b68ee",mediumspringgreen:"00fa9a",mediumturquoise:"48d1cc",mediumvioletred:"c71585",midnightblue:"191970",mintcream:"f5fffa",mistyrose:"ffe4e1",moccasin:"ffe4b5",navajowhite:"ffdead",navy:"000080",oldlace:"fdf5e6",olive:"808000",olivedrab:"6b8e23",orange:"ffa500",orangered:"ff4500",orchid:"da70d6",palegoldenrod:"eee8aa",palegreen:"98fb98",paleturquoise:"afeeee",palevioletred:"db7093",papayawhip:"ffefd5",peachpuff:"ffdab9",peru:"cd853f",pink:"ffc0cb",plum:"dda0dd",powderblue:"b0e0e6",purple:"800080",rebeccapurple:"663399",red:"f00",rosybrown:"bc8f8f",royalblue:"4169e1",saddlebrown:"8b4513",salmon:"fa8072",sandybrown:"f4a460",seagreen:"2e8b57",seashell:"fff5ee",sienna:"a0522d",silver:"c0c0c0",skyblue:"87ceeb",slateblue:"6a5acd",slategray:"708090",slategrey:"708090",snow:"fffafa",springgreen:"00ff7f",steelblue:"4682b4",tan:"d2b48c",teal:"008080",thistle:"d8bfd8",tomato:"ff6347",turquoise:"40e0d0",violet:"ee82ee",wheat:"f5deb3",white:"fff",whitesmoke:"f5f5f5",yellow:"ff0",yellowgreen:"9acd32"},A=i.hexNames=function(a){var b={};for(var c in a)a.hasOwnProperty(c)&&(b[a[c]]=c);return b}(z);function B(a){return(isNaN(a=parseFloat(a))||a<0||a>1)&&(a=1),a}function C(a,b){"string"==typeof(c=a)&&-1!=c.indexOf(".")&&1===parseFloat(c)&&(a="100%");var c,d,e="string"==typeof(d=a)&&-1!=d.indexOf("%");return(a=Math.min(b,Math.max(0,parseFloat(a))),e&&(a=parseInt(a*b,10)/100),1e-6>Math.abs(a-b))?1:a%b/parseFloat(b)}function D(a){return Math.min(1,Math.max(0,a))}function E(a){return parseInt(a,16)}function F(a){return 1==a.length?"0"+a:""+a}function G(a){return a<=1&&(a=100*a+"%"),a}function H(a){return Math.round(255*parseFloat(a)).toString(16)}var I=(c="[\\s|\\(]+("+(b="(?:[-\\+]?\\d*\\.\\d+%?)|(?:[-\\+]?\\d+%?)")+")[,|\\s]+("+b+")[,|\\s]+("+b+")\\s*\\)?",d="[\\s|\\(]+("+b+")[,|\\s]+("+b+")[,|\\s]+("+b+")[,|\\s]+("+b+")\\s*\\)?",{CSS_UNIT:new RegExp(b),rgb:RegExp("rgb"+c),rgba:RegExp("rgba"+d),hsl:RegExp("hsl"+c),hsla:RegExp("hsla"+d),hsv:RegExp("hsv"+c),hsva:RegExp("hsva"+d),hex3:/^#?([0-9a-fA-F]{1})([0-9a-fA-F]{1})([0-9a-fA-F]{1})$/,hex6:/^#?([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})$/,hex4:/^#?([0-9a-fA-F]{1})([0-9a-fA-F]{1})([0-9a-fA-F]{1})([0-9a-fA-F]{1})$/,hex8:/^#?([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})$/});function J(a){return!!I.CSS_UNIT.exec(a)}function K(a){return a<=.04045?a/12.92:Math.pow((a+.055)/1.055,2.4)}function L(a){let{r:b,g:c,b:d}=i(a).toRgb(),e=K(b/255),f=K(c/255),g=K(d/255),h=Math.cbrt(.4122214708*e+.5363325363*f+.0514459929*g),j=Math.cbrt(.2119034982*e+.6806995451*f+.1073969566*g),k=Math.cbrt(.0883024619*e+.2817188376*f+.6299787005*g),l=1.9779984951*h-2.428592205*j+.4505937099*k,m=.0259040371*h+.7827717662*j-.808675766*k,n=Math.sqrt(l*l+m*m),o=180/Math.PI*Math.atan2(m,l);o<0&&(o+=360);let p=(100*(.2104542553*h+.793617785*j-.0040720468*k)).toFixed(4),q=Number(n.toFixed(6)),r=Number(o.toFixed(3));return 0===q?`${p}% 0 0deg`:`${p}% ${q} ${r}deg`}let M=a=>i(a).isDark()?"100% 0 0deg":"0% 0 0deg",N=a=>i(a).isDark()?"#FFFFFF":"#000000",O=({bg:a,fg:b,primary:c})=>({"base-100":a,"base-200":i(a).darken(5).toHexString(),"base-300":i(a).darken(12).toHexString(),"base-content":b,neutral:i(a).darken(15).desaturate(20).toHexString(),"neutral-content":i(b).lighten(20).desaturate(20).toHexString(),primary:c,secondary:i(c).lighten(20).toHexString(),accent:i(c).analogous()[1].toHexString()}),P=({bg:a,fg:b,primary:c})=>({"base-100":a,"base-200":i(a).lighten(5).toHexString(),"base-300":i(a).lighten(12).toHexString(),"base-content":b,neutral:i(a).lighten(15).desaturate(20).toHexString(),"neutral-content":i(b).darken(20).desaturate(20).toHexString(),primary:c,secondary:i(c).darken(20).toHexString(),accent:i(c).triad()[1].toHexString()}),Q=[{name:"default",label:"Default",colors:{light:O({fg:"#171717",bg:"#ffffff",primary:"#0066cc"}),dark:P({fg:"#e0e0e0",bg:"#222222",primary:"#77bbee"})}},{name:"gray",label:"Gray",colors:{light:O({fg:"#222222",bg:"#e0e0e0",primary:"#4488cc"}),dark:P({fg:"#c6c6c6",bg:"#444444",primary:"#88ccee"})}},{name:"sepia",label:"Sepia",colors:{light:O({fg:"#5b4636",bg:"#f1e8d0",primary:"#008b8b"}),dark:P({fg:"#ffd595",bg:"#342e25",primary:"#48d1cc"})}},{name:"grass",label:"Grass",colors:{light:O({fg:"#232c16",bg:"#d7dbbd",primary:"#177b4d"}),dark:P({fg:"#d8deba",bg:"#333627",primary:"#a6d608"})}},{name:"cherry",label:"Cherry",colors:{light:O({fg:"#4e1609",bg:"#f0d1d5",primary:"#de3838"}),dark:P({fg:"#e5c4c8",bg:"#462f32",primary:"#ff646e"})}},{name:"sky",label:"Sky",colors:{light:O({fg:"#262d48",bg:"#cedef5",primary:"#2d53e5"}),dark:P({fg:"#babee1",bg:"#282e47",primary:"#ff646e"})}},{name:"solarized",label:"Solarized",colors:{light:O({fg:"#586e75",bg:"#fdf6e3",primary:"#268bd2"}),dark:P({fg:"#93a1a1",bg:"#002b36",primary:"#268bd2"})}},{name:"gruvbox",label:"Gruvbox",colors:{light:O({fg:"#3c3836",bg:"#fbf1c7",primary:"#076678"}),dark:P({fg:"#ebdbb2",bg:"#282828",primary:"#83a598"})}},{name:"nord",label:"Nord",colors:{light:O({fg:"#2e3440",bg:"#eceff4",primary:"#5e81ac"}),dark:P({fg:"#d8dee9",bg:"#2e3440",primary:"#88c0d0"})}},{name:"contrast",label:"Contrast",colors:{light:O({fg:"#000000",bg:"#ffffff",primary:"#4488cc"}),dark:P({fg:"#ffffff",bg:"#000000",primary:"#88ccee"})}},{name:"sunset",label:"Sunset",colors:{light:O({fg:"#423126",bg:"#fff7f0",primary:"#fe6b64"}),dark:P({fg:"#f6e1d7",bg:"#3c2b25",primary:"#ff9c94"})}}],R=(a,b=!1)=>{let c=`
    --b1: ${L(a["base-100"])};
    --b2: ${L(a["base-200"])};
    --b3: ${L(a["base-300"])};
    --bc: ${L(a["base-content"])};
    
    --p: ${L(a.primary)};
    --pc: ${M(a.primary)};
    
    --s: ${L(a.secondary)};
    --sc: ${M(a.secondary)};
    
    --a: ${L(a.accent)};
    --ac: ${M(a.accent)};
    
    --n: ${L(a.neutral)};
    --nc: ${L(a["neutral-content"])};
    
    --in: 69.37% 0.047 231deg;
    --inc: 100% 0 0deg;
    --su: 78.15% 0.12 160deg;
    --suc: 100% 0 0deg;
    --wa: 90.69% 0.123 84deg;
    --wac: 0% 0 0deg;
    --er: 70.9% 0.184 22deg;
    --erc: 100% 0 0deg;
  `,d=`
    --fallback-b1: ${a["base-100"]};
    --fallback-b2: ${a["base-200"]};
    --fallback-b3: ${a["base-300"]};
    --fallback-bc: ${a["base-content"]};

    --fallback-p: ${a.primary};
    --fallback-pc: ${N(a.primary)};

    --fallback-s: ${a.secondary};
    --fallback-sc: ${N(a.secondary)};

    --fallback-a: ${a.accent};
    --fallback-ac: ${N(a.accent)};

    --fallback-n: ${a.neutral};
    --fallback-nc: ${a["neutral-content"]};

    --fallback-in: #ff0000;
    --fallback-inc: #ffffff;
    --fallback-su: #00ff00;
    --fallback-suc: #000000;
    --fallback-wa: #ffff00;
    --fallback-wac: #000000;
    --fallback-er: #ff8000;
    --fallback-erc: #000000;
  `;return c+(b?d:"")};a.s(["applyCustomTheme",0,(a,b,c=!1)=>{if(!a&&!b)return;let d=a?`${a.name}-light`:`${b}-light`,e=a?`${a.name}-dark`:`${b}-dark`,f=a?O(a.colors.light):(Q.find(a=>a.name===b)||Q[0]).colors.light,g=a?P(a.colors.dark):(Q.find(a=>a.name===b)||Q[0]).colors.dark,h=`
    [data-theme="${d}"] {
      ${R(f,c)}
    }
    
    [data-theme="${e}"] {
      ${R(g,c)}
    }
    
    :root {
      --${d}: 1;
      --${e}: 1;
    }
  `,i=document.createElement("style");i.id=`theme-${a?a.name:b}-styles`,i.textContent=h;let j=document.getElementById(i.id);return j&&j.remove(),document.head.appendChild(i),{light:d,dark:e}},"generateDarkPalette",0,P,"generateLightPalette",0,O,"themes",0,Q],304830);var S=a.i(200515),T=a.i(411725),U=a.i(387431);let V=[{family:"Bitter",weights:"ital,wght@0,100..900;1,100..900"},{family:"Fira Code",weights:"wght@300..700"},{family:"Literata",weights:"ital,opsz,wght@0,7..72,200..900;1,7..72,200..900"},{family:"Merriweather",weights:"ital,opsz,wght@0,18..144,300..900;1,18..144,300..900"},{family:"Noto Sans",weights:"ital,wght@0,100..900;1,100..900"},{family:"Open Sans",weights:"ital,wght@0,300..800;1,300..800"},{family:"Roboto",weights:"ital,wght@0,100..900;1,100..900"},{family:"Roboto Slab",weights:"ital,wght@0,100..900;1,100..900"},{family:"Vollkorn",weights:"ital,wght@0,400..900;1,400..900"},{family:"PT Sans",weights:"ital,wght@0,400;0,700;1,400;1,700"},{family:"PT Serif",weights:"ital,wght@0,400;0,700;1,400;1,700"},{family:"PT Mono",weights:""}],W=[{family:"LXGW WenKai TC",weights:""},{family:"Noto Sans SC",weights:""},{family:"Noto Sans TC",weights:""},{family:"Noto Serif JP",weights:""}],X=async(a,b=!1)=>{let c=b||(0,S.isCJKEnv)(),d=`
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?${V.map(({family:a,weights:b})=>`family=${encodeURIComponent(a)}${b?`:${b}`:""}`).join("&")}&display=swap" crossorigin="anonymous">
`,e="";if(c&&(e=`
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
`,d=`${d}

  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/misans-webfont@1.0.4/misans-l3/misans-l3/result.min.css" crossorigin="anonymous" />
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/lxgw-wenkai-screen-web/1.520.0/lxgwwenkaigbscreen/result.css" crossorigin="anonymous" />
  <link rel="stylesheet" href="https://ik.imagekit.io/fonts14/packages/GuanKiapTsingKhai/dist/GuanKiapTsingKhai-T/result.css" crossorigin="anonymous" />
  <link rel="stylesheet" href="https://ik.imagekit.io/fonts14/packages/syst/dist/SourceHanSerifCN/result.css" crossorigin="anonymous" />
  <link rel="stylesheet" href="https://ik.imagekit.io/fonts14/packages/hwmct/dist/%E6%B1%87%E6%96%87%E6%98%8E%E6%9C%9D%E4%BD%93/result.css" crossorigin="anonymous" />
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?${W.map(({family:a,weights:b})=>`family=${encodeURIComponent(a)}${b?`:${b}`:""}`).join("&")}&display=swap" crossorigin="anonymous" />
`),e){let b=a.createElement("style");b.textContent=e,a.head.appendChild(b)}Array.from(new DOMParser().parseFromString(d,"text/html").head.children).forEach(b=>{if("LINK"===b.tagName){let c=a.createElement("link");c.rel=b.getAttribute("rel")||"",c.href=b.getAttribute("href")||"",c.crossOrigin=b.getAttribute("crossorigin")||"",a.head.appendChild(c)}})};function Y(a){switch(a.toLowerCase().split(".").pop()){case"ttf":default:return"ttf";case"otf":return"otf";case"woff":return"woff";case"woff2":return"woff2"}}function Z(a){let b={ttf:"truetype",otf:"opentype",woff:"woff",woff2:"woff2"}[Y(a.path)]||"truetype",c=(a.family||a.name).replace(/\s+/g," ").trim(),d=a.style||"normal",e=a.weight||400,f=a.variable||!1;if(!a.blobUrl)throw Error(`Blob URL not available for font: ${a.name}`);return`
    @font-face {
      font-family: "${c}";
      ${f?"":`font-style: ${d};`}
      ${f?"":`font-weight: ${e};`}
      src: url("${a.blobUrl}") format("${b}");
      font-display: swap;
    }
  `}a.s(["createCustomFont",0,function(a,b){let c=b?.name||(0,T.getFilename)(a).replace(/\.(ttf|otf|woff|woff2)$/i,"");return{...b,id:(0,U.md5Fingerprint)(c),name:c,path:a}},"createFontCSS",0,Z,"getFontFormat",0,Y,"getMimeType",0,function(a){return({ttf:"font/ttf",otf:"font/otf",woff:"font/woff",woff2:"font/woff2"})[a]||"font/ttf"},"mountAdditionalFonts",0,X,"mountCustomFont",0,(a,b)=>{let c=`custom-font-${b.id}`,d=a.getElementById(c)||a.createElement("style");d.id=c,d.textContent=Z(b),d.parentNode||a.head.appendChild(d)}],868949);let $="scroll-wrapper",_="scroll-wrapper-fit",aa=`.${$}`,ab="data-readest-scroll-wrapper-touch-scroll",ac=a=>a.scrollWidth-a.clientWidth>4,ad=a=>a.scrollHeight-a.clientHeight>4,ae=a=>{if(!a||!("closest"in a))return null;let b=a.closest(aa);for(;b;){if(ac(b)||ad(b))return b;b=b.parentElement?.closest(aa)??null}return null},af=["Top","Right","Bottom","Left"];a.s(["SCROLL_WRAPPER_CLASS",0,$,"SCROLL_WRAPPER_FIT_CLASS",0,_,"applyScrollableStyle",0,a=>{let b=a.defaultView,c=c=>{let d=c.parentElement;if(!d||d.classList.contains($))return;let e=a.createElement("div");e.className=$,e.setAttribute("cfi-skip",""),d.insertBefore(e,c),e.appendChild(c),((a,b,c)=>{if(!c)return;let d=a.style;if(!d)return;let e=c.getComputedStyle(a);for(let a of af){let c=`margin${a}`,f=e[c];0>parseFloat(f)&&(b.style[c]=f,d[c]="0px")}})(c,e,b),((a,b)=>{if(!b?.ResizeObserver)return;let c=new b.ResizeObserver(()=>{if(!(a.clientWidth<=0)){let b;b=a.scrollWidth-a.clientWidth<=4,a.classList.toggle(_,b),c.disconnect()}});c.observe(a)})(e,b)};a.querySelectorAll("table").forEach(c),a.querySelectorAll("math").forEach(a=>{(a=>{if("block"===a.getAttribute("display"))return!0;let b=a.parentElement;if(!b)return!1;for(let c of b.childNodes)if(c!==a&&(c.nodeType===Node.ELEMENT_NODE||c.nodeType===Node.TEXT_NODE&&c.textContent?.trim()))return!1;return!0})(a)&&c(a)})},"applyTableTouchScroll",0,a=>{let b=a.documentElement;if("true"===b.getAttribute(ab))return;b.setAttribute(ab,"true");let c=0,d=0,e=null,f=()=>{e=null},g={capture:!0,passive:!1};a.addEventListener("touchstart",a=>{if(!(e=ae(a.target)))return;let b=a.changedTouches[0];b&&(c=b.screenX,d=b.screenY)},g),a.addEventListener("touchmove",a=>{var b;if(!e||!e.contains(a.target))return;let f=a.changedTouches[0];if(!f)return;let g=f.screenX-c,h=f.screenY-d;b=e,(Math.abs(g)>Math.abs(h)?Math.abs(g)>=8&&ac(b):Math.abs(h)>=8&&ad(b))&&a.stopImmediatePropagation()},g),a.addEventListener("touchend",f,g),a.addEventListener("touchcancel",f,g),a.addEventListener("wheel",a=>{let b=ae(a.target);b&&(Math.abs(a.deltaX)>Math.abs(a.deltaY)?ac(b):ad(b))&&a.stopImmediatePropagation()},{capture:!0,passive:!0})}],851959);let ag=(a,b,c,d)=>{let f=["Georgia","Times New Roman"],g=[a,...d!==a?[d]:[],...e.SERIF_FONTS.filter(b=>b!==a&&b!==d&&!f.includes(b)),...e.CJK_SERIF_FONTS.filter(b=>b!==a&&b!==d),...f.filter(a=>e.SERIF_FONTS.includes(a)&&!f.includes(d)),...e.FALLBACK_FONTS],h=[b,...d!==b?[d]:[],...e.SANS_SERIF_FONTS.filter(a=>a!==b&&a!==d),...e.CJK_SANS_SERIF_FONTS.filter(a=>a!==b&&a!==d),...e.FALLBACK_FONTS],i=[c,...e.MONOSPACE_FONTS.filter(a=>a!==c)],j=a=>a.map(a=>`"${a}"`).join(", ");return{serif:`${j(g)}, serif`,sansSerif:`${j(h)}, sans-serif`,monospace:`${j(i)}, monospace`}},ah=()=>`
    ::selection {
      color: var(--theme-bg-color);
      background: var(--theme-fg-color);
    }
    ::-moz-selection {
      color: var(--theme-bg-color);
      background: var(--theme-fg-color);
    }
  `,ai=a=>`
  .translation-source {
  }
  .translation-target {
  }
  .translation-target.hidden {
    display: none !important;
  }
  .translation-target-block {
    display: block !important;
    ${a?"margin: 0.5em 0 !important;":""}
  }
  .translation-target-toc {
    display: block !important;
    overflow: hidden;
    text-overflow: ellipsis;
  }
`,aj=()=>{let a="default",b=Q.find(b=>b.name===a);if(!b){let c=[].find(b=>b.name===a);c&&(b={name:c.name,label:c.label,colors:{light:O(c.colors.light),dark:P(c.colors.dark)}})}b||(b=Q[0]);let c=(0,b.colors.light);return{bg:c["base-100"],fg:c["base-content"],primary:c.primary,palette:c,isDarkMode:!1}};a.s(["applyFixedlayoutStyles",0,(a,b,c)=>{c||(c=aj());let{bg:d,fg:e,primary:f,isDarkMode:g}=c,h=b.isEink,i=b.overrideColor,j=b.invertImgColorInDark,k=b.contrast??100,l=[];g&&j&&l.push("invert(100%)"),100!==k&&l.push(`contrast(${k}%)`);let m=l.length?`filter: ${l.join(" ")};`:"",n="fixed-layout-styles",o=a.getElementById(n);o&&o.remove(),(o=a.createElement("style")).id=n,o.textContent=`
    html {
      --theme-bg-color: ${d};
      --theme-fg-color: ${e};
      --theme-primary-color: ${f};
      color-scheme: ${g?"dark":"light"};
    }
    body {
      position: relative;
      background-color: var(--theme-bg-color);
    }
    ${h?ah():""}
    #canvas {
      display: inline-block;
      width: fit-content;
      height: fit-content;
      background-color: var(--theme-bg-color);
    }
    img, canvas {
      ${m}
      ${i?`mix-blend-mode: ${g?"#000000"===d?"luminosity":"overlay":"multiply"};`:""}
    }
    img.singlePage {
      position: relative;
    }
  `,a.head.appendChild(o)},"applyImageStyle",0,a=>{let b=a.defaultView??window;for(let{img:c,percentWidth:d,percentHeight:e,inlineWithText:f,keepBaseline:g}of Array.from(a.querySelectorAll("img")).map(a=>{let c=a.getAttribute("width"),d=c&&(c.endsWith("%")||c.endsWith("vw"))?parseFloat(c):NaN,e=a.getAttribute("height"),f=e&&(e.endsWith("%")||e.endsWith("vh"))?parseFloat(e):NaN,g=!1,h=!1,i=a.parentNode;if(i&&i.nodeType===Node.ELEMENT_NODE){let c=Array.from(i.childNodes),d=c.some(a=>a.nodeType===Node.TEXT_NODE&&a.textContent?.trim()),e=c.every(a=>a.nodeType!==Node.ELEMENT_NODE||"BR"!==a.tagName);if(g=d&&e){let c=b.getComputedStyle(a).verticalAlign;h=""===c||"baseline"===c}}return{img:a,percentWidth:d,percentHeight:f,inlineWithText:g,keepBaseline:h}}))isNaN(d)||(c.style.width=`${d/100*window.innerWidth}px`,c.removeAttribute("width")),isNaN(e)||(c.style.height=`${e/100*window.innerHeight}px`,c.removeAttribute("height")),f&&(c.classList.add("has-text-siblings"),g&&c.classList.add("has-text-siblings-baseline"));a.querySelectorAll("hr").forEach(a=>{let b=window.getComputedStyle(a);b.backgroundImage&&"none"!==b.backgroundImage&&a.classList.add("background-img")})},"applyScrollModeClass",0,(a,b)=>{a.body.classList.remove("scroll-mode","paginated-mode"),a.body.classList.add(b?"scroll-mode":"paginated-mode")},"applyScrollbarStyle",0,(a,b)=>{let c="scrollbar-hide-style",d=a.getElementById(c);b?(d||((d=a.createElement("style")).id=c,a.head.appendChild(d)),d.textContent="foliate-view::part(container) { scrollbar-width: none; }"):d&&(d.textContent="foliate-view::part(container) { scrollbar-width: thin; }")},"applyThemeModeClass",0,(a,b)=>{a.body.classList.remove("theme-light","theme-dark"),a.body.classList.add(b?"theme-dark":"theme-light")},"applyTranslationStyle",0,a=>{let b="translation-style",c=document.getElementById(b);c&&c.remove();let d=document.createElement("style");d.id=b,d.textContent=ai(a.showTranslateSource),document.head.appendChild(d)},"getBaseFontFamily",0,a=>{let b=ag(a.serifFont,a.sansSerifFont,a.monospaceFont,a.defaultCJKFont);return"serif"===a.defaultFont.toLowerCase()?b.serif:b.sansSerif},"getDictStyles",0,(a,b,c)=>`
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
      ${c?`background-color: color-mix(in srgb, ${a} 80%, #000);`:""}
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
`,"getStyles",0,(a,b,c=[])=>{var d,e,f,g,h,i,j,k,l;let m,n,o,p,q,r,s,t,u,v,w,x,y,z,A,B,C,D,E;b||(b=aj());let F=(m=a.marginTopPx,n=a.marginRightPx,o=a.marginBottomPx,p=a.marginLeftPx,q=a.writingMode,r=a.vertical,`
  html {
    --margin-top: ${m}px;
    --margin-right: ${n}px;
    --margin-bottom: ${o}px;
    --margin-left: ${p}px;
  }
  html, body {
    ${"auto"===q?"":`writing-mode: ${q} !important;`}
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

  .${$} {
    display: block;
    overflow: auto;
    max-width: 100%;
    touch-action: pan-x pan-y;
    scrollbar-width: thin;
    -webkit-overflow-scrolling: touch;
  }
  .${_} {
    overflow: visible;
  }
  .${$} > table {
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
    ${r?"width: 1em;":"height: 1em;"}
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
`),G=a.useBookLayout?"":(s=a.overrideLayout,t=a.paragraphMargin,u=a.lineHeight,v=a.wordSpacing,w=a.letterSpacing,x=a.textIndent,y=a.fullJustification,z=a.hyphenation,A=a.vertical,`
  html {
    --default-text-align: ${y?"justify":"start"};
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
    line-height: ${u} ${s?"!important":""};
    word-spacing: ${v}px ${s?"!important":""};
    letter-spacing: ${w}px ${s?"!important":""};
    text-indent: ${x}em ${s?"!important":""};
    -webkit-hyphens: ${z?"auto":"manual"} ${s?"!important":""};
    hyphens: ${z?"auto":"manual"} ${s?"!important":""};
    -webkit-hyphenate-limit-before: 3;
    -webkit-hyphenate-limit-after: 2;
    -webkit-hyphenate-limit-lines: 2;
    hanging-punctuation: allow-end last;
    widows: 2;
  }
  li {
    line-height: ${u} ${s?"!important":""};
    -webkit-hyphens: ${z?"auto":"manual"} ${s?"!important":""};
    hyphens: ${z?"auto":"manual"} ${s?"!important":""};
  }
  p.aligned-center, blockquote.aligned-center,
  dd.aligned-center, div.aligned-center {
    text-align: center ${s?"!important":""};
  }
  p.aligned-left, blockquote.aligned-left,
  dd.aligned-left, div.aligned-left {
    ${y&&s?"text-align: justify !important;":""}
  }
  p.aligned-right, blockquote.aligned-right,
  dd.aligned-right, div.aligned-right {
    text-align: right ${s?"!important":""};
  }
  p.aligned-justify, blockquote.aligned-justify,
  dd.aligned-justify, div.aligned-justify {
    ${!y&&s?"text-align: initial !important;":""};
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
    ${A?`margin-left: ${t}em ${s?"!important":""};`:""}
    ${A?`margin-right: ${t}em ${s?"!important":""};`:""}
    ${A?`margin-top: unset ${s?"!important":""};`:""}
    ${A?`margin-bottom: unset ${s?"!important":""};`:""}
    ${!A?`margin-top: ${t}em ${s?"!important":""};`:""}
    ${!A?`margin-bottom: ${t}em ${s?"!important":""};`:""}
    ${!A?`margin-left: unset ${s?"!important":""};`:""}
    ${!A?`margin-right: unset ${s?"!important":""};`:""}
  }
  div {
    ${A&&s?`margin-left: ${t}em !important;`:""}
    ${A&&s?`margin-right: ${t}em !important;`:""}
    ${!A&&s?`margin-top: ${t}em !important;`:""}
    ${!A&&s?`margin-bottom: ${t}em !important;`:""}
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
    ${A?"transform: rotate(90deg);":""}
    ${A?"transform-origin: center;":""}
    ${A?"height: 2em;":""}
    ${A?`width: ${u}em;`:""}
    ${A?"vertical-align: unset;":""}
  }

  .nonindent, .noindent {
    text-indent: unset !important;
  }
`),H=["ios","android"].includes((0,S.getOSPlatform)()),I=(a.zoomLevel||100)/100,J=(d=a.serifFont,e=a.sansSerifFont,f=a.monospaceFont,g=a.defaultFont,h=a.defaultCJKFont,i=a.defaultFontSize*(H?1.25:1)*I,j=a.minimumFontSize,k=a.fontWeight,l=a.overrideFont,B=ag(d,e,f,h),C="serif"===g.toLowerCase()?"--serif":"--sans-serif",`
    html {
      --serif: ${B.serif};
      --sans-serif: ${B.sansSerif};
      --monospace: ${B.monospace};
      --font-size: ${i}px;
      --min-font-size: ${j}px;
      --font-weight: ${k};
    }
    html, body {
      font-size: ${i}px !important;
      font-weight: ${k};
      -webkit-text-size-adjust: none;
      text-size-adjust: none;
    }
    /* lower specificity than ebook built-in font styles */
    html {
      font-family: var(${C}) ${l?"!important":""};
    }
    /* higher specificity than ebook built-in font styles */
    html body {
      ${l?`font-family: var(${C}) !important;`:""}
    }
    font[size="1"] {
      font-size: ${j}px;
    }
    font[size="2"] {
      font-size: ${1.5*j}px;
    }
    font[size="3"] {
      font-size: ${i}px;
    }
    font[size="4"] {
      font-size: ${1.2*i}px;
    }
    font[size="5"] {
      font-size: ${1.5*i}px;
    }
    font[size="6"] {
      font-size: ${2*i}px;
    }
    font[size="7"] {
      font-size: ${3*i}px;
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
      ${l?"font-family: revert !important;":""}
    }
  `),K=c.filter(a=>!!a.blobUrl).map(a=>{try{return Z(a)}catch{return""}}).join("\n"),L=((a,b,c,d,e)=>{let{bg:f,fg:g,primary:h,isDarkMode:i}=c,j=!!d&&"none"!==d;return`
    html {
      --bg-texture-id: ${d};
      --theme-bg-color: ${f};
      --theme-fg-color: ${g};
      --theme-primary-color: ${h};
      --override-color: ${a};
      color-scheme: ${i?"dark":"light"};
    }
    html, body {
      color: ${g};
    }
    ${e?ah():""}
    html[has-background], body[has-background] {
      --background-set: var(--theme-bg-color);
    }
    html {
      background-color: var(--theme-bg-color, transparent);
      background: var(--background-set, none);
    }
    body {
      ${e?`background-color: ${f} !important;`:""}
    }
    section, aside, blockquote, article, nav, header, footer, main, figure,
    div, p, font, h1, h2, h3, h4, h5, h6, li, span {
      ${a&&!j?`background-color: ${f} !important;`:""}
      ${a&&!j?`color: ${g} !important;`:""}
      ${a&&!j?`border-color: ${g} !important;`:""}
    }
    pre, span { /* inline code blocks */
      ${a?`background-color: ${f} !important;`:""}
    }
    a:any-link {
      ${a?`color: ${h} !important;`:i?"color: lightblue;":""}
      text-decoration: ${e?"underline":"none"};
    }
    body.pbg {
      ${i?`background-color: ${f} !important;`:""}
    }
    img {
      ${i&&b?"filter: invert(100%);":""}
      ${i&&a?"filter: grayscale(100%) contrast(1.2) brightness(1.2);":""}
      ${a?"mix-blend-mode: multiply;":""}
    }
    svg, img {
      ${a?"background-color: transparent !important;":""};
    }
    /* horizontal rule #1649 */
    *:has(> hr.background-img):not(body) {
      background-color: ${f};
    }
    hr.background-img {
      mix-blend-mode: multiply;
    }
    p[width][height] > img:only-child {
      mix-blend-mode: multiply;
    }
    /* inline images */
    *:has(> img.has-text-siblings):not(body) {
      ${a?`background-color: ${f};`:""}
    }
    p img.has-text-siblings, span img.has-text-siblings, sup img.has-text-siblings {
      mix-blend-mode: ${i?"screen":"multiply"};
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
      ${i?`color: ${g}cc;`:""}
      ${i?`background: color-mix(in srgb, ${f} 90%, #000);`:""}
      ${i?`background-color: color-mix(in srgb, ${f} 90%, #000);`:""}
    }
    blockquote {
      ${i?`background: color-mix(in srgb, ${f} 80%, #000);`:""}
    }
    /* Only tint table descendants when the user has opted into color override.
       By default, leave them transparent so a plain table (and the invisible
       spacer cells some books use for vertical layout) keeps the page
       background instead of a different shade. Illegible light/zebra table
       backgrounds are handled separately by the dark-mode light-background
       rewriters (getDarkModeLightBackgroundOverrides / transformStylesheet).
       See #4419 (and #2377, which this gate originally fixed). */
    blockquote, table * {
      ${i&&a?`background: color-mix(in srgb, ${f} 80%, #000);`:""}
      ${i&&a?`background-color: color-mix(in srgb, ${f} 80%, #000);`:""}
    }
    /* override inline hardcoded text color */
    font[color="#000000"], font[color="#000"], font[color="black"],
    font[color="rgb(0,0,0)"], font[color="rgb(0, 0, 0)"],
    *[style*="color: rgb(0,0,0)"], *[style*="color: rgb(0, 0, 0)"],
    *[style*="color: #000"], *[style*="color: #000000"], *[style*="color: black"],
    *[style*="color:rgb(0,0,0)"], *[style*="color:rgb(0, 0, 0)"],
    *[style*="color:#000"], *[style*="color:#000000"], *[style*="color:black"] {
      color: ${g} !important;
    }
    ${i&&!a?`
    /* Callout boxes often use inline white/light backgrounds while html/body set dark fg. */
    *[style*="background-color: #fff"], *[style*="background-color:#fff"],
    *[style*="background-color: #ffffff"], *[style*="background-color:#ffffff"],
    *[style*="background-color: white"], *[style*="background-color:white"],
    *[style*="background: #fff"], *[style*="background:#fff"],
    *[style*="background: #ffffff"], *[style*="background:#ffffff"],
    *[style*="background: white"], *[style*="background:white"],
    *[style*="background-color: rgb(255"], *[style*="background-color:rgb(255"],
    *[style*="background: rgb(255"], *[style*="background:rgb(255"] {
      background-color: ${f} !important;
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
      background-color: ${f} !important;
    }
    .calibre {
      color: unset;
      background-color: unset;
    }
  `})(a.overrideColor,a.invertImgColorInDark,b,a.backgroundTextureId,a.isEink),M=ai(a.showTranslateSource),N=`
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
`,O=(D=a.wordLensGlossFontSize||.5,E=a.wordLensGlossColor||"",`
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
    font-size: ${D}em;
    line-height: 1.1;
    ${E?`color: ${E};
    opacity: 1;`:"opacity: 0.7;"}
    font-weight: normal;
    text-align: center;
  }
`),P=a.userStylesheet;return`@namespace epub "http://www.idpf.org/2007/ops";
${K}
${F}
${G}
${J}
${L}
${M}
${N}
${O}
${P}`},"getThemeCode",0,aj,"keepTextAlignment",0,a=>{let b=a.defaultView??window,c=a.querySelectorAll("div, p, blockquote, dd"),d=Array(c.length);for(let a=0;a<c.length;a++){let e=b.getComputedStyle(c[a]).textAlign;"center"===e?d[a]="aligned-center":"left"===e?d[a]="aligned-left":"right"===e?d[a]="aligned-right":"justify"===e?d[a]="aligned-justify":d[a]=null}for(let a=0;a<c.length;a++){let b=d[a];b&&c[a].classList.add(b)}},"transformStylesheet",0,(a,b,c,d)=>{let e=["ios","android"].includes((0,S.getOSPlatform)())?1.25:1,f=!a.includes("{"),g=/([^{]+)({[^}]+})/g;a=(a=a.replace(g,(a,b,c)=>{let d=/text-align\s*:\s*center\s*[;$]/.test(c),e=/text-indent\s*:\s*0(?:\.0+)?(?:px|em|rem|%)?\s*[;$]/.test(c);return d&&e?b+(c=(c=c.replace(/(text-align\s*:\s*center)(\s*;|\s*$)/g,"$1 !important$2")).replace(/(text-indent\s*:\s*0(?:\.0+)?(?:px|em|rem|%)?)(\s*;|\s*$)/g,"$1 !important$2")):a})).replace(g,(a,b,c)=>/white-space\s*:\s*nowrap\s*[;$]/.test(c)?(/overflow\s*:/.test(c)||(c=c.replace(/}$/," overflow: clip !important; }")),b+c):a),f?/page-break-after\s*:\s*always\s*[;]?/.test(a)&&!/margin-bottom\s*:/.test(a)&&(a=a.replace(/;?\s*$/,"")+"; margin-bottom: calc(var(--available-height) * 1px)"):a=a.replace(g,(a,b,c)=>/page-break-after\s*:\s*always\s*[;$]/.test(c)?(/margin-bottom\s*:/.test(c)||(c=c.replace(/}$/," margin-bottom: calc(var(--available-height) * 1px); }")),b+c):a),a=(a=(a=(a=a.replace(g,(a,b,c)=>{if(d)return b+c;let e=[],f=!1;for(let a of["top","bottom","left","right"]){let b=RegExp(`duokan-bleed\\s*:\\s*[^;]*${a}[^;]*;`),d=RegExp(`margin-${a}\\s*:`);b.test(c)&&!d.test(c)&&(f=!0,e.push(a),c=c.replace(/}$/,` margin-${a}: calc(-1 * var(--page-margin-${a})) !important; }`))}return f&&(/position\s*:/.test(c)||(c=c.replace(/}$/," position: relative !important; }")),/overflow\s*:/.test(c)||(c=c.replace(/}$/," overflow: hidden !important; }")),/display\s*:/.test(c)||(c=c.replace(/}$/," display: flow-root !important; }")),e.includes("left")&&e.includes("right")&&(c=c.replace(/}$/," width: calc(var(--full-width) * 1px) !important; }").replace(/}$/," min-width: calc(var(--full-width) * 1px) !important; }").replace(/}$/," max-width: calc(var(--full-width) * 1px) !important; }")),e.includes("top")&&e.includes("bottom")&&(c=c.replace(/}$/," height: calc(var(--full-height) * 1px) !important; }").replace(/}$/," min-height: calc(var(--full-height) * 1px) !important; }").replace(/}$/," max-height: calc(var(--full-height) * 1px) !important; }"))),b+c})).replace(g,(a,b,c)=>{if(/\bbody\b/i.test(b)){let a=/font-family\s*:\s*serif\s*(?:;|\}|$)/.test(c),b=/font-family\s*:\s*sans-serif\s*(?:;|\}|$)/.test(c);a&&(c=c.replace(/font-family\s*:\s*serif\s*(;|\}|$)/gi,"font-family: unset$1")),b&&(c=c.replace(/font-family\s*:\s*sans-serif\s*(;|\}|$)/gi,"font-family: unset$1"))}return b+c})).replace(g,(a,c,d)=>{let e=/(?:^|[^a-z-])width\s*:\s*(\d+(?:\.\d+)?)px/.exec(d);return(e?parseFloat(e[1]??"0"):0)>b&&!/max-width\s*:/.test(d)?c+(d=d.replace(/}$/," width: 100%; max-width: calc(var(--available-width) * 1px); box-sizing: border-box; }")):a})).replace(/font-size\s*:\s*xx-small/gi,"font-size: 0.6rem").replace(/font-size\s*:\s*x-small/gi,"font-size: 0.75rem").replace(/font-size\s*:\s*small/gi,"font-size: 0.875rem").replace(/font-size\s*:\s*medium/gi,"font-size: 1rem").replace(/font-size\s*:\s*large/gi,"font-size: 1.2rem").replace(/font-size\s*:\s*x-large/gi,"font-size: 1.5rem").replace(/font-size\s*:\s*xx-large/gi,"font-size: 2rem").replace(/font-size\s*:\s*xxx-large/gi,"font-size: 3rem").replace(/font-size\s*:\s*(\d+(?:\.\d+)?)px/gi,(a,b)=>{let c=parseFloat(b)/e/16;return`font-size: ${c}rem`}).replace(/font-size\s*:\s*(\d+(?:\.\d+)?)pt/gi,(a,b)=>{let c=parseFloat(b)/e/12;return`font-size: ${c}rem`}).replace(/font-size\s*:\s*(\d*\.?\d+)(px|rem|em|%)?/gi,(a,b,c="px")=>`font-size: max(${b}${c}, var(--min-font-size, 8px))`).replace(/backdrop-filter\s*:\s*brightness\(100%\)\s*[;]?/gi,"").replace(/(\d*\.?\d+)vw/gi,(a,c)=>parseFloat(c)*b/100+"px").replace(/(\d*\.?\d+)vh/gi,(a,b)=>parseFloat(b)*c/100+"px").replace(/([\s;])-webkit-user-select\s*:\s*none/gi,"$1-webkit-user-select: unset").replace(/([\s;])-moz-user-select\s*:\s*none/gi,"$1-moz-user-select: unset").replace(/([\s;])-ms-user-select\s*:\s*none/gi,"$1-ms-user-select: unset").replace(/([\s;])-o-user-select\s*:\s*none/gi,"$1-o-user-select: unset").replace(/([\s;])user-select\s*:\s*none/gi,"$1user-select: unset").replace(/(font-family\s*:[^;]*?)\bsans-serif\b/gi,"$1MYBOOKS_SS_PLACEHOLDER").replace(/(font-family\s*:[^;]*?)\bserif\b(?!-)/gi,"$1var(--serif, serif)").replace(/MYBOOKS_SS_PLACEHOLDER/g,"var(--sans-serif, sans-serif)").replace(/(font-family\s*:[^;]*?)\bmonospace\b/gi,"$1var(--monospace, monospace)").replace(/([\s;])font-weight\s*:\s*normal/gi,"$1font-weight: var(--font-weight)").replace(/([\s;])color\s*:\s*black/gi,"$1color: var(--theme-fg-color)").replace(/([\s;])color\s*:\s*#000000/gi,"$1color: var(--theme-fg-color)").replace(/([\s;])color\s*:\s*#000/gi,"$1color: var(--theme-fg-color)").replace(/([\s;])color\s*:\s*rgb\(0,\s*0,\s*0\)/gi,"$1color: var(--theme-fg-color)");let{isDarkMode:h,bg:i}=aj();return h&&(a=a.replace(g,(a,b,c)=>{let d=c.replace(/background(-color)?\s*:\s*([^;!}]+)(\s*!important)?(?=\s*[;!}])/gi,(a,b,c,d)=>(a=>{let b=a.trim().toLowerCase();if("white"===b)return!0;let c=b.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);if(c){let a=c[1],b=3===a.length?a.split("").map(a=>a+a).join(""):a;return(.299*parseInt(b.slice(0,2),16)+.587*parseInt(b.slice(2,4),16)+.114*parseInt(b.slice(4,6),16))/255>.85}let d=b.match(/^rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)$/);return d?.[1]!=null&&null!=d[2]&&null!=d[3]&&(.299*parseInt(d[1],10)+.587*parseInt(d[2],10)+.114*parseInt(d[3],10))/255>.85})(c.trim().split(/\s+/)[0]??"")?`background-color: ${i}${d??""}`:a);return d===c?a:b+d})),a}],436676)},636276,888614,a=>{"use strict";var b=a.i(169710),c=a.i(436676),d=a.i(198746);a.i(317797);var e=a.i(949545);let f=(0,b.create)((a,b)=>({themeMode:"auto",themeColor:"default",systemIsDarkMode:!1,isDarkMode:!1,themeCode:(0,c.getThemeCode)(),systemUIVisible:!1,statusBarHeight:24,systemUIAlwaysHidden:!1,safeAreaInsets:{top:0,right:0,bottom:0,left:0},isRoundedWindow:!0,showSystemUI:()=>a({systemUIVisible:!0}),dismissSystemUI:()=>a({systemUIVisible:!1}),setStatusBarHeight:b=>a({statusBarHeight:b}),setSystemUIAlwaysHidden:b=>a({systemUIAlwaysHidden:b}),getIsDarkMode:()=>b().isDarkMode,setThemeMode:d=>{let e="dark"===d||"auto"===d&&b().systemIsDarkMode;document.documentElement.setAttribute("data-theme",`${b().themeColor}-${e?"dark":"light"}`),a({themeMode:d,isDarkMode:e}),a({themeCode:(0,c.getThemeCode)()})},setThemeColor:d=>{document.documentElement.setAttribute("data-theme",`${d}-${b().isDarkMode?"dark":"light"}`),a({themeColor:d}),a({themeCode:(0,c.getThemeCode)()})},updateAppTheme:a=>{if((0,e.isWebAppPlatform)()){let{palette:c}=b().themeCode;document.querySelector('meta[name="theme-color"]')?.setAttribute("content",c[a])}},saveCustomTheme:async(a,b,c,d)=>{let e=b.globalReadSettings.customThemes||[],f=e.findIndex(a=>a.name===c.name);d?f>-1&&e.splice(f,1):f>-1?e[f]=c:e.push(c),b.globalReadSettings.customThemes=e,localStorage.setItem("customThemes",JSON.stringify(e));let g=await a.getAppService();await g.saveSettings(b)},handleSystemThemeChange:d=>{let e=b().themeMode,f="dark"===e||"auto"===e&&d;document.documentElement.setAttribute("data-theme",`${b().themeColor}-${f?"dark":"light"}`),a({systemIsDarkMode:d,isDarkMode:f}),a({themeCode:(0,c.getThemeCode)()})},updateSafeAreaInsets:b=>{a({safeAreaInsets:b})}}));a.s(["initSystemThemeListener",0,a=>{},"loadDataTheme",0,()=>{if("u"<typeof localStorage||"u"<typeof document)return;let a=localStorage.getItem("themeMode"),b=localStorage.getItem("themeColor");if(a&&b){let c=window.matchMedia("(prefers-color-scheme: dark)").matches;document.documentElement.setAttribute("data-theme",`${b}-${"dark"===a||"auto"===a&&c?"dark":"light"}`)}},"useThemeStore",0,f],636276);var g=a.i(410981),h=a.i(546158),i=a.i(200515);a.s(["useSafeAreaInsets",0,()=>{let{appService:a}=(0,h.useEnv)(),b=(0,g.useRef)({top:0,right:0,bottom:0,left:0}),{updateSafeAreaInsets:c}=f(),e=a=>{let{top:d,right:e,bottom:f,left:g}=b.current;(a.top!==d||a.right!==e||a.bottom!==f||a.left!==g)&&(b.current=a,c(a))},j=(0,g.useCallback)(()=>{if(!a)return;if(!a.hasSafeAreaInset)return void e(b.current);let c=getComputedStyle(document.documentElement),f=c.getPropertyValue("--safe-area-inset-top");a.isIOSApp&&"macos"===(0,i.getOSPlatform)()?e({top:0,right:0,bottom:0,left:0}):a.isAndroidApp||a.isIOSApp?(0,d.getSafeAreaInsets)().then(a=>{a.error?console.error("Error getting safe area insets from native bridge:",a.error):e({top:Math.round(a.top),right:Math.round(a.right),bottom:Math.round(a.bottom),left:Math.round(a.left)})}):f&&e({top:Math.round(parseFloat(c.getPropertyValue("--safe-area-inset-top"))||0),right:Math.round(parseFloat(c.getPropertyValue("--safe-area-inset-right"))||0),bottom:Math.round(parseFloat(c.getPropertyValue("--safe-area-inset-bottom"))||0),left:Math.round(parseFloat(c.getPropertyValue("--safe-area-inset-left"))||0)})},[a]);return(0,g.useEffect)(()=>{j(),window.screen?.orientation?window.screen.orientation.addEventListener("change",j):window.addEventListener("orientationchange",j);let a=()=>{"visible"===document.visibilityState&&j()};document.addEventListener("visibilitychange",a);let b=()=>{j()};return window.addEventListener("focus",b),()=>{window.screen?.orientation?window.screen.orientation.removeEventListener("change",j):window.removeEventListener("orientationchange",j),document.removeEventListener("visibilitychange",a),window.removeEventListener("focus",b)}},[j]),{onUpdateInsets:j}}],888614)},239337,a=>{"use strict";function b(){for(var a,b,c=0,d="",e=arguments.length;c<e;c++)(a=arguments[c])&&(b=function a(b){var c,d,e="";if("string"==typeof b||"number"==typeof b)e+=b;else if("object"==typeof b)if(Array.isArray(b)){var f=b.length;for(c=0;c<f;c++)b[c]&&(d=a(b[c]))&&(e&&(e+=" "),e+=d)}else for(d in b)b[d]&&(e&&(e+=" "),e+=d);return e}(a))&&(d&&(d+=" "),d+=b);return d}a.s(["clsx",0,b,"default",0,b])},393886,a=>{"use strict";var b=a.i(49426);a.s(["MdAdd",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"},child:[]}]})(a)},"MdAlarm",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"m22 5.72-4.6-3.86-1.29 1.53 4.6 3.86L22 5.72zM7.88 3.39 6.6 1.86 2 5.71l1.29 1.53 4.59-3.85zM12.5 8H11v6l4.75 2.85.75-1.23-4-2.37V8zM12 4c-4.97 0-9 4.03-9 9s4.02 9 9 9a9 9 0 0 0 0-18zm0 16c-3.87 0-7-3.13-7-7s3.13-7 7-7 7 3.13 7 7-3.13 7-7 7z"},child:[]}]})(a)},"MdArrowBack",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z"},child:[]}]})(a)},"MdArrowBackIosNew",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M17.77 3.77 16 2 6 12l10 10 1.77-1.77L9.54 12z"},child:[]}]})(a)},"MdArrowDownward",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"m20 12-1.41-1.41L13 16.17V4h-2v12.17l-5.58-5.59L4 12l8 8 8-8z"},child:[]}]})(a)},"MdArrowDropDown",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"m7 10 5 5 5-5z"},child:[]}]})(a)},"MdArrowForwardIos",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M6.23 20.23 8 22l10-10L8 2 6.23 3.77 14.46 12z"},child:[]}]})(a)},"MdArrowUpward",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"m4 12 1.41 1.41L11 7.83V20h2V7.83l5.58 5.59L20 12l-8-8-8 8z"},child:[]}]})(a)},"MdAutoStories",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"m19 1-5 5v11l5-4.5V1zM1 6v14.65c0 .25.25.5.5.5.1 0 .15-.05.25-.05C3.1 20.45 5.05 20 6.5 20c1.95 0 4.05.4 5.5 1.5V6c-1.45-1.1-3.55-1.5-5.5-1.5S2.45 4.9 1 6zm22 13.5V6c-.6-.45-1.25-.75-2-1v13.5c-1.1-.35-2.3-.5-3.5-.5-1.7 0-4.15.65-5.5 1.5v2c1.35-.85 3.8-1.5 5.5-1.5 1.65 0 3.35.3 4.75 1.05.1.05.15.05.25.05.25 0 .5-.25.5-.5v-1.1z"},child:[]}]})(a)},"MdBook",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M18 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zM6 4h5v8l-2.5-1.5L6 12V4z"},child:[]}]})(a)},"MdBookmarkAdd",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M21 7h-2v2h-2V7h-2V5h2V3h2v2h2v2zm-2 14-7-3-7 3V5c0-1.1.9-2 2-2h7a5.002 5.002 0 0 0 5 7.9V21z"},child:[]}]})(a)},"MdBookmarkBorder",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M17 3H7c-1.1 0-1.99.9-1.99 2L5 21l7-3 7 3V5c0-1.1-.9-2-2-2zm0 15-5-2.18L7 18V5h10v13z"},child:[]}]})(a)},"MdBusiness",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 7V3H2v18h20V7H12zM6 19H4v-2h2v2zm0-4H4v-2h2v2zm0-4H4V9h2v2zm0-4H4V5h2v2zm4 12H8v-2h2v2zm0-4H8v-2h2v2zm0-4H8V9h2v2zm0-4H8V5h2v2zm10 12h-8v-2h2v-2h-2v-2h2v-2h-2V9h8v10zm-2-8h-2v2h2v-2zm0 4h-2v2h2v-2z"},child:[]}]})(a)},"MdCancel",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 2C6.47 2 2 6.47 2 12s4.47 10 10 10 10-4.47 10-10S17.53 2 12 2zm5 13.59L15.59 17 12 13.41 8.41 17 7 15.59 10.59 12 7 8.41 8.41 7 12 10.59 15.59 7 17 8.41 13.41 12 17 15.59z"},child:[]}]})(a)},"MdCategory",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"m12 2-5.5 9h11z"},child:[]},{tag:"circle",attr:{cx:"17.5",cy:"17.5",r:"4.5"},child:[]},{tag:"path",attr:{d:"M3 13.5h8v8H3z"},child:[]}]})(a)},"MdCheck",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"},child:[]}]})(a)},"MdCheckCircle",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"},child:[]}]})(a)},"MdCheckCircleOutline",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0zm0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M16.59 7.58 10 14.17l-3.59-3.58L5 12l5 5 8-8zM12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8z"},child:[]}]})(a)},"MdChecklist",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M22 7h-9v2h9V7zm0 8h-9v2h9v-2zM5.54 11 2 7.46l1.41-1.41 2.12 2.12 4.24-4.24 1.41 1.41L5.54 11zm0 8L2 15.46l1.41-1.41 2.12 2.12 4.24-4.24 1.41 1.41L5.54 19z"},child:[]}]})(a)},"MdChevronLeft",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M15.41 7.41 14 6l-6 6 6 6 1.41-1.41L10.83 12z"},child:[]}]})(a)},"MdChevronRight",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M10 6 8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z"},child:[]}]})(a)},"MdClose",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"},child:[]}]})(a)},"MdCloudDownload",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M19.35 10.04A7.49 7.49 0 0 0 12 4C9.11 4 6.6 5.64 5.35 8.04A5.994 5.994 0 0 0 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96zM17 13l-5 5-5-5h3V9h4v4h3z"},child:[]}]})(a)},"MdCloudSync",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M21.5 14.98c-.02 0-.03 0-.05.01A3.49 3.49 0 0 0 18 12c-1.4 0-2.6.83-3.16 2.02A2.988 2.988 0 0 0 12 17c0 1.66 1.34 3 3 3l6.5-.02a2.5 2.5 0 0 0 0-5zM10 4.26v2.09C7.67 7.18 6 9.39 6 12c0 1.77.78 3.34 2 4.44V14h2v6H4v-2h2.73A7.942 7.942 0 0 1 4 12c0-3.73 2.55-6.85 6-7.74zM20 6h-2.73a7.98 7.98 0 0 1 2.66 5h-2.02c-.23-1.36-.93-2.55-1.91-3.44V10h-2V4h6v2z"},child:[]}]})(a)},"MdCloudUpload",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M19.35 10.04A7.49 7.49 0 0 0 12 4C9.11 4 6.6 5.64 5.35 8.04A5.994 5.994 0 0 0 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96zM14 13v4h-4v-4H7l5-5 5 5h-3z"},child:[]}]})(a)},"MdCollectionsBookmark",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M4 6H2v14c0 1.1.9 2 2 2h14v-2H4V6z"},child:[]},{tag:"path",attr:{d:"M20 2H8c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 10-2.5-1.5L15 12V4h5v8z"},child:[]}]})(a)},"MdContentCopy",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"},child:[]}]})(a)},"MdContrast",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 22c5.52 0 10-4.48 10-10S17.52 2 12 2 2 6.48 2 12s4.48 10 10 10zm1-17.93c3.94.49 7 3.85 7 7.93s-3.05 7.44-7 7.93V4.07z"},child:[]}]})(a)},"MdDelete",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"},child:[]}]})(a)},"MdDeleteOutline",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM8 9h8v10H8V9zm7.5-5-1-1h-5l-1 1H5v2h14V4z"},child:[]}]})(a)},"MdDeleteSweep",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M15 16h4v2h-4zm0-8h7v2h-7zm0 4h6v2h-6zM3 18c0 1.1.9 2 2 2h6c1.1 0 2-.9 2-2V8H3v10zM14 5h-3l-1-1H6L5 5H2v2h12z"},child:[]}]})(a)},"MdDevices",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M4 6h18V4H4c-1.1 0-2 .9-2 2v11H0v3h14v-3H4V6zm19 2h-6c-.55 0-1 .45-1 1v10c0 .55.45 1 1 1h6c.55 0 1-.45 1-1V9c0-.55-.45-1-1-1zm-1 9h-4v-7h4v7z"},child:[]}]})(a)},"MdDownload",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M5 20h14v-2H5v2zM19 9h-4V3H9v6H5l7 7 7-7z"},child:[]}]})(a)},"MdDownloadForOffline",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 2C6.49 2 2 6.49 2 12s4.49 10 10 10 10-4.49 10-10S17.51 2 12 2zm-1 8V6h2v4h3l-4 4-4-4h3zm6 7H7v-2h10v2z"},child:[]}]})(a)},"MdDragIndicator",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M11 18c0 1.1-.9 2-2 2s-2-.9-2-2 .9-2 2-2 2 .9 2 2zm-2-8c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0-6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm6 4c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z"},child:[]}]})(a)},"MdEdit",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a.996.996 0 0 0 0-1.41l-2.34-2.34a.996.996 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"},child:[]}]})(a)},"MdError",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"},child:[]}]})(a)},"MdErrorOutline",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M11 15h2v2h-2zm0-8h2v6h-2zm.99-5C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8z"},child:[]}]})(a)},"MdExpandLess",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"m12 8-6 6 1.41 1.41L12 10.83l4.59 4.58L18 14z"},child:[]}]})(a)},"MdExpandMore",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M16.59 8.59 12 13.17 7.41 8.59 6 10l6 6 6-6z"},child:[]}]})(a)},"MdFavorite",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"m12 21.35-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"},child:[]}]})(a)},"MdFileUpload",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M9 16h6v-6h4l-7-7-7 7h4zm-4 2h14v2H5z"},child:[]}]})(a)},"MdFolder",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M10 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z"},child:[]}]})(a)},"MdFolderCopy",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M3 6H1v13c0 1.1.9 2 2 2h17v-2H3V6z"},child:[]},{tag:"path",attr:{d:"M21 4h-7l-2-2H7c-1.1 0-1.99.9-1.99 2L5 15c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2z"},child:[]}]})(a)},"MdFolderOff",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M20 6h-8l-2-2H6.83l14.93 14.93c.15-.28.24-.59.24-.93V8c0-1.1-.9-2-2-2zM2.1 2.1.69 3.51l1.56 1.56c-.15.28-.24.59-.24.93L2 18c0 1.1.9 2 2 2h13.17l3.31 3.31 1.41-1.41L2.1 2.1z"},child:[]}]})(a)},"MdFolderOpen",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M20 6h-8l-2-2H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2zm0 12H4V8h16v10z"},child:[]}]})(a)},"MdGraphicEq",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M7 18h2V6H7v12zm4 4h2V2h-2v20zm-8-8h2v-4H3v4zm12 4h2V6h-2v12zm4-8v4h2v-4h-2z"},child:[]}]})(a)},"MdHeadphones",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 3a9 9 0 0 0-9 9v7c0 1.1.9 2 2 2h4v-8H5v-1c0-3.87 3.13-7 7-7s7 3.13 7 7v1h-4v8h4c1.1 0 2-.9 2-2v-7a9 9 0 0 0-9-9z"},child:[]}]})(a)},"MdHome",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z"},child:[]}]})(a)},"MdInfoOutline",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M11 7h2v2h-2V7zm0 4h2v6h-2v-6zm1-9C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z"},child:[]}]})(a)},"MdInsertDriveFile",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M6 2c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6H6zm7 7V3.5L18.5 9H13z"},child:[]}]})(a)},"MdKeyboardArrowDown",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M7.41 8.59 12 13.17l4.59-4.58L18 10l-6 6-6-6 1.41-1.41z"},child:[]}]})(a)},"MdKeyboardArrowLeft",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M15.41 16.59 10.83 12l4.58-4.59L14 6l-6 6 6 6 1.41-1.41z"},child:[]}]})(a)},"MdKeyboardArrowRight",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M8.59 16.59 13.17 12 8.59 7.41 10 6l6 6-6 6-1.41-1.41z"},child:[]}]})(a)},"MdKeyboardArrowUp",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M7.41 15.41 12 10.83l4.59 4.58L18 14l-6-6-6 6z"},child:[]}]})(a)},"MdKeyboardDoubleArrowLeft",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M17.59 18 19 16.59 14.42 12 19 7.41 17.59 6l-6 6z"},child:[]},{tag:"path",attr:{d:"m11 18 1.41-1.41L7.83 12l4.58-4.59L11 6l-6 6z"},child:[]}]})(a)},"MdKeyboardDoubleArrowRight",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M6.41 6 5 7.41 9.58 12 5 16.59 6.41 18l6-6z"},child:[]},{tag:"path",attr:{d:"m13 6-1.41 1.41L16.17 12l-4.58 4.59L13 18l6-6z"},child:[]}]})(a)},"MdLibraryAddCheck",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M20 2H8c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-7.53 12L9 10.5l1.4-1.41 2.07 2.08L17.6 6 19 7.41 12.47 14zM4 6H2v14c0 1.1.9 2 2 2h14v-2H4V6z"},child:[]}]})(a)},"MdLink",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M3.9 12c0-1.71 1.39-3.1 3.1-3.1h4V7H7c-2.76 0-5 2.24-5 5s2.24 5 5 5h4v-1.9H7c-1.71 0-3.1-1.39-3.1-3.1zM8 13h8v-2H8v2zm9-6h-4v1.9h4c1.71 0 3.1 1.39 3.1 3.1s-1.39 3.1-3.1 3.1h-4V17h4c2.76 0 5-2.24 5-5s-2.24-5-5-5z"},child:[]}]})(a)},"MdLocalOffer",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"m21.41 11.58-9-9C12.05 2.22 11.55 2 11 2H4c-1.1 0-2 .9-2 2v7c0 .55.22 1.05.59 1.42l9 9c.36.36.86.58 1.41.58.55 0 1.05-.22 1.41-.59l7-7c.37-.36.59-.86.59-1.41 0-.55-.23-1.06-.59-1.42zM5.5 7C4.67 7 4 6.33 4 5.5S4.67 4 5.5 4 7 4.67 7 5.5 6.33 7 5.5 7z"},child:[]}]})(a)},"MdLock",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z"},child:[]}]})(a)},"MdLockOpen",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 17c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm6-9h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6h1.9c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm0 12H6V10h12v10z"},child:[]}]})(a)},"MdLogout",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"m17 7-1.41 1.41L18.17 11H8v2h10.17l-2.58 2.58L17 17l5-5zM4 5h8V3H4c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h8v-2H4V5z"},child:[]}]})(a)},"MdNightlightRound",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M12.01 12c0-3.57 2.2-6.62 5.31-7.87.89-.36.75-1.69-.19-1.9-1.1-.24-2.27-.3-3.48-.14-4.51.6-8.12 4.31-8.59 8.83C4.44 16.93 9.13 22 15.01 22c.73 0 1.43-.08 2.12-.23.95-.21 1.1-1.53.2-1.9A8.46 8.46 0 0 1 12.01 12z"},child:[]}]})(a)},"MdNoteAdd",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 14h-3v3h-2v-3H8v-2h3v-3h2v3h3v2zm-3-7V3.5L18.5 9H13z"},child:[]}]})(a)},"MdOfflinePin",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10 10-4.5 10-10S17.5 2 12 2zm5 16H7v-2h10v2zm-6.7-4L7 10.7l1.4-1.4 1.9 1.9 5.3-5.3L17 7.3 10.3 14z"},child:[]}]})(a)},"MdOpenInNew",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M19 19H5V5h7V3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14c1.1 0 2-.9 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z"},child:[]}]})(a)},"MdOutlineAutoMode",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M19.03 3.56c-1.67-1.39-3.74-2.3-6.03-2.51v2.01c1.73.19 3.31.88 4.61 1.92l1.42-1.42zM11 3.06V1.05c-2.29.2-4.36 1.12-6.03 2.51l1.42 1.42A8.928 8.928 0 0 1 11 3.06zM4.98 6.39 3.56 4.97C2.17 6.64 1.26 8.71 1.05 11h2.01c.19-1.73.88-3.31 1.92-4.61zM20.94 11h2.01c-.21-2.29-1.12-4.36-2.51-6.03l-1.42 1.42A8.928 8.928 0 0 1 20.94 11zM7 12l3.44 1.56L12 17l1.56-3.44L17 12l-3.44-1.56L12 7l-1.56 3.44z"},child:[]},{tag:"path",attr:{d:"M12 21a8.96 8.96 0 0 1-7.46-4H7v-2H1v6h2v-2.7c1.99 2.84 5.27 4.7 9 4.7 4.87 0 9-3.17 10.44-7.56l-1.96-.45C19.25 18.48 15.92 21 12 21z"},child:[]}]})(a)},"MdOutlineCancel",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z",opacity:".87"},child:[]},{tag:"path",attr:{d:"M12 2C6.47 2 2 6.47 2 12s4.47 10 10 10 10-4.47 10-10S17.53 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm3.59-13L12 10.59 8.41 7 7 8.41 10.59 12 7 15.59 8.41 17 12 13.41 15.59 17 17 15.59 13.41 12 17 8.41z"},child:[]}]})(a)},"MdOutlineCheck",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41L9 16.17z"},child:[]}]})(a)},"MdOutlineCloudDownload",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M19.35 10.04A7.49 7.49 0 0 0 12 4C9.11 4 6.6 5.64 5.35 8.04A5.994 5.994 0 0 0 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96zM19 18H6c-2.21 0-4-1.79-4-4 0-2.05 1.53-3.76 3.56-3.97l1.07-.11.5-.95A5.469 5.469 0 0 1 12 6c2.62 0 4.88 1.86 5.39 4.43l.3 1.5 1.53.11A2.98 2.98 0 0 1 22 15c0 1.65-1.35 3-3 3zm-5.55-8h-2.9v3H8l4 4 4-4h-2.55z"},child:[]}]})(a)},"MdOutlineCloudOff",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M24 15c0-2.64-2.05-4.78-4.65-4.96A7.49 7.49 0 0 0 12 4c-1.33 0-2.57.36-3.65.97l1.49 1.49C10.51 6.17 11.23 6 12 6c3.04 0 5.5 2.46 5.5 5.5v.5H19a2.996 2.996 0 0 1 1.79 5.4l1.41 1.41c1.09-.92 1.8-2.27 1.8-3.81zM4.41 3.86 3 5.27l2.77 2.77h-.42A5.994 5.994 0 0 0 0 14c0 3.31 2.69 6 6 6h11.73l2 2 1.41-1.41L4.41 3.86zM6 18c-2.21 0-4-1.79-4-4s1.79-4 4-4h1.73l8 8H6z"},child:[]}]})(a)},"MdOutlineCloudQueue",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M19.35 10.04A7.49 7.49 0 0 0 12 4C9.11 4 6.6 5.64 5.35 8.04A5.994 5.994 0 0 0 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96zM19 18H6c-2.21 0-4-1.79-4-4s1.79-4 4-4h.71C7.37 7.69 9.48 6 12 6c3.04 0 5.5 2.46 5.5 5.5v.5H19c1.66 0 3 1.34 3 3s-1.34 3-3 3z"},child:[]}]})(a)},"MdOutlineCloudUpload",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M19.35 10.04A7.49 7.49 0 0 0 12 4C9.11 4 6.6 5.64 5.35 8.04A5.994 5.994 0 0 0 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96zM19 18H6c-2.21 0-4-1.79-4-4 0-2.05 1.53-3.76 3.56-3.97l1.07-.11.5-.95A5.469 5.469 0 0 1 12 6c2.62 0 4.88 1.86 5.39 4.43l.3 1.5 1.53.11A2.98 2.98 0 0 1 22 15c0 1.65-1.35 3-3 3zM8 13h2.55v3h2.9v-3H16l-4-4z"},child:[]}]})(a)},"MdOutlineDarkMode",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M9.37 5.51A7.35 7.35 0 0 0 9.1 7.5c0 4.08 3.32 7.4 7.4 7.4.68 0 1.35-.09 1.99-.27A7.014 7.014 0 0 1 12 19c-3.86 0-7-3.14-7-7 0-2.93 1.81-5.45 4.37-6.49zM12 3a9 9 0 1 0 9 9c0-.46-.04-.92-.1-1.36a5.389 5.389 0 0 1-4.4 2.26 5.403 5.403 0 0 1-3.14-9.8c-.44-.06-.9-.1-1.36-.1z"},child:[]}]})(a)},"MdOutlineDelete",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M16 9v10H8V9h8m-1.5-6h-5l-1 1H5v2h14V4h-3.5l-1-1zM18 7H6v12c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7z"},child:[]}]})(a)},"MdOutlineDownload",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M19 9h-4V3H9v6H5l7 7 7-7zm-8 2V5h2v6h1.17L12 13.17 9.83 11H11zm-6 7h14v2H5z"},child:[]}]})(a)},"MdOutlineEdit",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"m14.06 9.02.92.92L5.92 19H5v-.92l9.06-9.06M17.66 3c-.25 0-.51.1-.7.29l-1.83 1.83 3.75 3.75 1.83-1.83a.996.996 0 0 0 0-1.41l-2.34-2.34c-.2-.2-.45-.29-.71-.29zm-3.6 3.19L3 17.25V21h3.75L17.81 9.94l-3.75-3.75z"},child:[]}]})(a)},"MdOutlineFileDownload",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M18 15v3H6v-3H4v3c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2v-3h-2zm-1-4-1.41-1.41L13 12.17V4h-2v8.17L8.41 9.59 7 11l5 5 5-5z"},child:[]}]})(a)},"MdOutlineForum",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M15 4v7H5.17L4 12.17V4h11m1-2H3c-.55 0-1 .45-1 1v14l4-4h10c.55 0 1-.45 1-1V3c0-.55-.45-1-1-1zm5 4h-2v9H6v2c0 .55.45 1 1 1h11l4 4V7c0-.55-.45-1-1-1z"},child:[]}]})(a)},"MdOutlineFullscreen",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z"},child:[]}]})(a)},"MdOutlineHeadphones",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 3a9 9 0 0 0-9 9v7c0 1.1.9 2 2 2h4v-8H5v-1c0-3.87 3.13-7 7-7s7 3.13 7 7v1h-4v8h4c1.1 0 2-.9 2-2v-7a9 9 0 0 0-9-9zM7 15v4H5v-4h2zm12 4h-2v-4h2v4z"},child:[]}]})(a)},"MdOutlineInfo",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M11 7h2v2h-2zm0 4h2v6h-2zm1-9C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z"},child:[]}]})(a)},"MdOutlineLibraryAddCheck",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{d:"M20 4v12H8V4h12m0-2H8c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-7.53 12L9 10.5l1.4-1.41 2.07 2.08L17.6 6 19 7.41 12.47 14zM4 6H2v14c0 1.1.9 2 2 2h14v-2H4V6z"},child:[]},{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]}]})(a)},"MdOutlineLightMode",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 9c1.65 0 3 1.35 3 3s-1.35 3-3 3-3-1.35-3-3 1.35-3 3-3m0-2c-2.76 0-5 2.24-5 5s2.24 5 5 5 5-2.24 5-5-2.24-5-5-5zM2 13h2c.55 0 1-.45 1-1s-.45-1-1-1H2c-.55 0-1 .45-1 1s.45 1 1 1zm18 0h2c.55 0 1-.45 1-1s-.45-1-1-1h-2c-.55 0-1 .45-1 1s.45 1 1 1zM11 2v2c0 .55.45 1 1 1s1-.45 1-1V2c0-.55-.45-1-1-1s-1 .45-1 1zm0 18v2c0 .55.45 1 1 1s1-.45 1-1v-2c0-.55-.45-1-1-1s-1 .45-1 1zM5.99 4.58a.996.996 0 0 0-1.41 0 .996.996 0 0 0 0 1.41l1.06 1.06c.39.39 1.03.39 1.41 0s.39-1.03 0-1.41L5.99 4.58zm12.37 12.37a.996.996 0 0 0-1.41 0 .996.996 0 0 0 0 1.41l1.06 1.06c.39.39 1.03.39 1.41 0a.996.996 0 0 0 0-1.41l-1.06-1.06zm1.06-10.96a.996.996 0 0 0 0-1.41.996.996 0 0 0-1.41 0l-1.06 1.06c-.39.39-.39 1.03 0 1.41s1.03.39 1.41 0l1.06-1.06zM7.05 18.36a.996.996 0 0 0 0-1.41.996.996 0 0 0-1.41 0l-1.06 1.06c-.39.39-.39 1.03 0 1.41s1.03.39 1.41 0l1.06-1.06z"},child:[]}]})(a)},"MdOutlineMenu",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M3 18h18v-2H3v2zm0-5h18v-2H3v2zm0-7v2h18V6H3z"},child:[]}]})(a)},"MdOutlineNoAccounts",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M15.18 10.94c.2-.44.32-.92.32-1.44C15.5 7.57 13.93 6 12 6c-.52 0-1 .12-1.44.32l4.62 4.62z"},child:[]},{tag:"path",attr:{d:"M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zM4 12c0-1.85.63-3.55 1.69-4.9l2.86 2.86a3.47 3.47 0 0 0 2.99 2.99l2.2 2.2c-.57-.1-1.15-.15-1.74-.15-2.32 0-4.45.8-6.14 2.12A7.957 7.957 0 0 1 4 12zm8 8c-1.74 0-3.34-.56-4.65-1.5C8.66 17.56 10.26 17 12 17s3.34.56 4.65 1.5c-1.31.94-2.91 1.5-4.65 1.5zm6.31-3.1L7.1 5.69A7.902 7.902 0 0 1 12 4c4.42 0 8 3.58 8 8 0 1.85-.63 3.54-1.69 4.9z"},child:[]}]})(a)},"MdOutlinePause",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M6 19h4V5H6v14zm8-14v14h4V5h-4z"},child:[]}]})(a)},"MdOutlinePushPin",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M14 4v5c0 1.12.37 2.16 1 3H9c.65-.86 1-1.9 1-3V4h4m3-2H7c-.55 0-1 .45-1 1s.45 1 1 1h1v5c0 1.66-1.34 3-3 3v2h5.97v7l1 1 1-1v-7H19v-2c-1.66 0-3-1.34-3-3V4h1c.55 0 1-.45 1-1s-.45-1-1-1z"},child:[]}]})(a)},"MdOutlineRestartAlt",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M6 13c0-1.65.67-3.15 1.76-4.24L6.34 7.34A8.014 8.014 0 0 0 4 13c0 4.08 3.05 7.44 7 7.93v-2.02c-2.83-.48-5-2.94-5-5.91zm14 0c0-4.42-3.58-8-8-8-.06 0-.12.01-.18.01l1.09-1.09L11.5 2.5 8 6l3.5 3.5 1.41-1.41-1.08-1.08c.06 0 .12-.01.17-.01 3.31 0 6 2.69 6 6 0 2.97-2.17 5.43-5 5.91v2.02c3.95-.49 7-3.85 7-7.93z"},child:[]}]})(a)},"MdOutlineScreenRotation",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M16.48 2.52c3.27 1.55 5.61 4.72 5.97 8.48h1.5C23.44 4.84 18.29 0 12 0l-.66.03 3.81 3.81 1.33-1.32zm-6.25-.77a1.49 1.49 0 0 0-2.12 0L1.75 8.11a1.49 1.49 0 0 0 0 2.12l12.02 12.02c.59.59 1.54.59 2.12 0l6.36-6.36c.59-.59.59-1.54 0-2.12L10.23 1.75zm4.6 19.44L2.81 9.17l6.36-6.36 12.02 12.02-6.36 6.36zm-7.31.29A10.487 10.487 0 0 1 1.55 13H.05C.56 19.16 5.71 24 12 24l.66-.03-3.81-3.81-1.33 1.32z"},child:[]}]})(a)},"MdOutlineTextRotationNone",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"m21 18-3-3v2H5v2h13v2l3-3zM9.5 11.8h5l.9 2.2h2.1L12.75 3h-1.5L6.5 14h2.1l.9-2.2zM12 4.98 13.87 10h-3.74L12 4.98z"},child:[]}]})(a)},"MdOutlineThumbUpOffAlt",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M9 21h9c.83 0 1.54-.5 1.84-1.22l3.02-7.05c.09-.23.14-.47.14-.73v-2c0-1.1-.9-2-2-2h-6.31l.95-4.57.03-.32c0-.41-.17-.79-.44-1.06L14.17 1 7.58 7.59C7.22 7.95 7 8.45 7 9v10c0 1.1.9 2 2 2zM9 9l4.34-4.34L12 10h9v2l-3 7H9V9zM1 9h4v12H1V9z"},child:[]}]})(a)},"MdPause",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M6 19h4V5H6v14zm8-14v14h4V5h-4z"},child:[]}]})(a)},"MdPauseCircleFilled",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 14H9V8h2v8zm4 0h-2V8h2v8z"},child:[]}]})(a)},"MdPeople",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z"},child:[]}]})(a)},"MdPersonOutline",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 5.9a2.1 2.1 0 1 1 0 4.2 2.1 2.1 0 0 1 0-4.2m0 9c2.97 0 6.1 1.46 6.1 2.1v1.1H5.9V17c0-.64 3.13-2.1 6.1-2.1M12 4C9.79 4 8 5.79 8 8s1.79 4 4 4 4-1.79 4-4-1.79-4-4-4zm0 9c-2.67 0-8 1.34-8 4v3h16v-3c0-2.66-5.33-4-8-4z"},child:[]}]})(a)},"MdPhoneAndroid",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M16 1H8C6.34 1 5 2.34 5 4v16c0 1.66 1.34 3 3 3h8c1.66 0 3-1.34 3-3V4c0-1.66-1.34-3-3-3zm-2 20h-4v-1h4v1zm3.25-3H6.75V4h10.5v14z"},child:[]}]})(a)},"MdPlayArrow",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M8 5v14l11-7z"},child:[]}]})(a)},"MdPlayCircleFilled",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 14.5v-9l6 4.5-6 4.5z"},child:[]}]})(a)},"MdPlayCircleOutline",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"m10 16.5 6-4.5-6-4.5v9zM12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z"},child:[]}]})(a)},"MdPushPin",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{fillRule:"evenodd",d:"M16 9V4h1c.55 0 1-.45 1-1s-.45-1-1-1H7c-.55 0-1 .45-1 1s.45 1 1 1h1v5c0 1.66-1.34 3-3 3v2h5.97v7l1 1 1-1v-7H19v-2c-1.66 0-3-1.34-3-3z"},child:[]}]})(a)},"MdRadioButtonChecked",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 7c-2.76 0-5 2.24-5 5s2.24 5 5 5 5-2.24 5-5-2.24-5-5-5zm0-5C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8z"},child:[]}]})(a)},"MdRadioButtonUnchecked",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8z"},child:[]}]})(a)},"MdRefresh",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M17.65 6.35A7.958 7.958 0 0 0 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08A5.99 5.99 0 0 1 12 18c-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"},child:[]}]})(a)},"MdRemove",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M19 13H5v-2h14v2z"},child:[]}]})(a)},"MdRssFeed",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"circle",attr:{cx:"6.18",cy:"17.82",r:"2.18"},child:[]},{tag:"path",attr:{d:"M4 4.44v2.83c7.03 0 12.73 5.7 12.73 12.73h2.83c0-8.59-6.97-15.56-15.56-15.56zm0 5.66v2.83c3.9 0 7.07 3.17 7.07 7.07h2.83c0-5.47-4.43-9.9-9.9-9.9z"},child:[]}]})(a)},"MdSaveAlt",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M19 12v7H5v-7H3v7c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2v-7h-2zm-6 .67 2.59-2.58L17 11.5l-5 5-5-5 1.41-1.41L11 12.67V3h2z"},child:[]}]})(a)},"MdSearch",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"},child:[]}]})(a)},"MdSettings",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.488.488 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"},child:[]}]})(a)},"MdShield",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 1 3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4z"},child:[]}]})(a)},"MdSkipNext",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"m6 18 8.5-6L6 6v12zM16 6v12h2V6h-2z"},child:[]}]})(a)},"MdSkipPrevious",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M6 6h2v12H6zm3.5 6 8.5 6V6z"},child:[]}]})(a)},"MdSpeed",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"m20.38 8.57-1.23 1.85a8 8 0 0 1-.22 7.58H5.07A8 8 0 0 1 15.58 6.85l1.85-1.23A10 10 0 0 0 3.35 19a2 2 0 0 0 1.72 1h13.85a2 2 0 0 0 1.74-1 10 10 0 0 0-.27-10.44zm-9.79 6.84a2 2 0 0 0 2.83 0l5.66-8.49-8.49 5.66a2 2 0 0 0 0 2.83z"},child:[]}]})(a)},"MdStar",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 17.27 18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"},child:[]}]})(a)},"MdStarBorder",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"m22 9.24-7.19-.62L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21 12 17.27 18.18 21l-1.63-7.03L22 9.24zM12 15.4l-3.76 2.27 1-4.28-3.32-2.88 4.38-.38L12 6.1l1.71 4.04 4.38.38-3.32 2.88 1 4.28L12 15.4z"},child:[]}]})(a)},"MdStop",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M6 6h12v12H6z"},child:[]}]})(a)},"MdSync",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46A7.93 7.93 0 0 0 20 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74A7.93 7.93 0 0 0 4 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z"},child:[]}]})(a)},"MdSyncProblem",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M3 12c0 2.21.91 4.2 2.36 5.64L3 20h6v-6l-2.24 2.24A6.003 6.003 0 0 1 5 12a5.99 5.99 0 0 1 4-5.65V4.26C5.55 5.15 3 8.27 3 12zm8 5h2v-2h-2v2zM21 4h-6v6l2.24-2.24A6.003 6.003 0 0 1 19 12a5.99 5.99 0 0 1-4 5.65v2.09c3.45-.89 6-4.01 6-7.74 0-2.21-.91-4.2-2.36-5.64L21 4zm-10 9h2V7h-2v6z"},child:[]}]})(a)},"MdTextRotateVertical",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M15.75 5h-1.5L9.5 16h2.1l.9-2.2h5l.9 2.2h2.1L15.75 5zm-2.62 7L15 6.98 16.87 12h-3.74zM6 19.75l3-3H7V4.25H5v12.5H3l3 3z"},child:[]}]})(a)},"MdTranslate",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"m12.87 15.07-2.54-2.51.03-.03A17.52 17.52 0 0 0 14.07 6H17V4h-7V2H8v2H1v1.99h11.17C11.5 7.92 10.44 9.75 9 11.35 8.07 10.32 7.3 9.19 6.69 8h-2c.73 1.63 1.73 3.17 2.98 4.56l-5.09 5.02L4 19l5-5 3.11 3.11.76-2.04zM18.5 10h-2L12 22h2l1.12-3h4.75L21 22h2l-4.5-12zm-2.62 7 1.62-4.33L19.12 17h-3.24z"},child:[]}]})(a)},"MdVisibility",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"},child:[]}]})(a)},"MdVisibilityOff",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0zm0 0h24v24H0zm0 0h24v24H0zm0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M12 7c2.76 0 5 2.24 5 5 0 .65-.13 1.26-.36 1.83l2.92 2.92c1.51-1.26 2.7-2.89 3.43-4.75-1.73-4.39-6-7.5-11-7.5-1.4 0-2.74.25-3.98.7l2.16 2.16C10.74 7.13 11.35 7 12 7zM2 4.27l2.28 2.28.46.46A11.804 11.804 0 0 0 1 12c1.73 4.39 6 7.5 11 7.5 1.55 0 3.03-.3 4.38-.84l.42.42L19.73 22 21 20.73 3.27 3 2 4.27zM7.53 9.8l1.55 1.55c-.05.21-.08.43-.08.65 0 1.66 1.34 3 3 3 .22 0 .44-.03.65-.08l1.55 1.55c-.67.33-1.41.53-2.2.53-2.76 0-5-2.24-5-5 0-.79.2-1.53.53-2.2zm4.31-.78 3.15 3.15.02-.16c0-1.66-1.34-3-3-3l-.17.01z"},child:[]}]})(a)},"MdVolumeUp",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0z"},child:[]},{tag:"path",attr:{d:"M3 9v6h4l5 5V4L7 9H3zm13.5 3A4.5 4.5 0 0 0 14 7.97v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"},child:[]}]})(a)},"MdZoomIn",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"},child:[]},{tag:"path",attr:{d:"M12 10h-2v2H9v-2H7V9h2V7h1v2h2v1z"},child:[]}]})(a)},"MdZoomOut",0,function(a){return(0,b.GenIcon)({tag:"svg",attr:{viewBox:"0 0 24 24"},child:[{tag:"path",attr:{fill:"none",d:"M0 0h24v24H0V0z"},child:[]},{tag:"path",attr:{d:"M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14zM7 9h5v1H7z"},child:[]}]})(a)}])},75576,332359,a=>{"use strict";var b,c,d=a.i(409422),e=a.i(501427),f=a.i(785008),g=a.i(317797);function h(){return new k((0,g.getCurrentWindow)(),window.__TAURI_INTERNALS__.metadata.currentWebview.label,{skip:!0})}async function i(){return(0,f.invoke)("plugin:webview|get_all_webviews").then(a=>a.map(a=>new k(new g.Window(a.windowLabel,{skip:!0}),a.label,{skip:!0})))}let j=["tauri://created","tauri://error"];class k{constructor(a,b,c){this.window=a,this.label=b,this.listeners=Object.create(null),(null==c?void 0:c.skip)||(0,f.invoke)("plugin:webview|create_webview",{windowLabel:a.label,options:{...c,label:b}}).then(async()=>this.emit("tauri://created")).catch(async a=>this.emit("tauri://error",a))}static async getByLabel(a){var b;return null!=(b=(await i()).find(b=>b.label===a))?b:null}static getCurrent(){return h()}static async getAll(){return i()}async listen(a,b){return this._handleTauriEvent(a,b)?()=>{let c=this.listeners[a];c.splice(c.indexOf(b),1)}:(0,e.listen)(a,b,{target:{kind:"Webview",label:this.label}})}async once(a,b){return this._handleTauriEvent(a,b)?()=>{let c=this.listeners[a];c.splice(c.indexOf(b),1)}:(0,e.once)(a,b,{target:{kind:"Webview",label:this.label}})}async emit(a,b){if(j.includes(a)){for(let c of this.listeners[a]||[])c({event:a,id:-1,payload:b});return}return(0,e.emit)(a,b)}async emitTo(a,b,c){if(j.includes(b)){for(let a of this.listeners[b]||[])a({event:b,id:-1,payload:c});return}return(0,e.emitTo)(a,b,c)}_handleTauriEvent(a,b){return!!j.includes(a)&&(a in this.listeners?this.listeners[a].push(b):this.listeners[a]=[b],!0)}async position(){return(0,f.invoke)("plugin:webview|webview_position",{label:this.label}).then(a=>new d.PhysicalPosition(a))}async size(){return(0,f.invoke)("plugin:webview|webview_size",{label:this.label}).then(a=>new d.PhysicalSize(a))}async close(){return(0,f.invoke)("plugin:webview|webview_close",{label:this.label})}async setSize(a){return(0,f.invoke)("plugin:webview|set_webview_size",{label:this.label,value:a instanceof d.Size?a:new d.Size(a)})}async setPosition(a){return(0,f.invoke)("plugin:webview|set_webview_position",{label:this.label,value:a instanceof d.Position?a:new d.Position(a)})}async setFocus(){return(0,f.invoke)("plugin:webview|set_webview_focus",{label:this.label})}async setAutoResize(a){return(0,f.invoke)("plugin:webview|set_webview_auto_resize",{label:this.label,value:a})}async hide(){return(0,f.invoke)("plugin:webview|webview_hide",{label:this.label})}async show(){return(0,f.invoke)("plugin:webview|webview_show",{label:this.label})}async setZoom(a){return(0,f.invoke)("plugin:webview|set_webview_zoom",{label:this.label,value:a})}async reparent(a){return(0,f.invoke)("plugin:webview|reparent",{label:this.label,window:"string"==typeof a?a:a.label})}async clearAllBrowsingData(){return(0,f.invoke)("plugin:webview|clear_all_browsing_data")}async setBackgroundColor(a){return(0,f.invoke)("plugin:webview|set_webview_background_color",{color:a})}async onDragDropEvent(a){let b=await this.listen(e.TauriEvent.DRAG_ENTER,b=>{a({...b,payload:{type:"enter",paths:b.payload.paths,position:new d.PhysicalPosition(b.payload.position)}})}),c=await this.listen(e.TauriEvent.DRAG_OVER,b=>{a({...b,payload:{type:"over",position:new d.PhysicalPosition(b.payload.position)}})}),f=await this.listen(e.TauriEvent.DRAG_DROP,b=>{a({...b,payload:{type:"drop",paths:b.payload.paths,position:new d.PhysicalPosition(b.payload.position)}})}),g=await this.listen(e.TauriEvent.DRAG_LEAVE,b=>{a({...b,payload:{type:"leave"}})});return()=>{b(),f(),c(),g()}}}async function l(){return(0,f.invoke)("plugin:window|get_all_windows").then(a=>a.map(a=>new m(a,{skip:!0})))}a.s(["Webview",0,k,"getCurrentWebview",0,h],332359);class m{constructor(a,b={}){var c;this.label=a,this.listeners=Object.create(null),(null==b?void 0:b.skip)||(0,f.invoke)("plugin:webview|create_webview_window",{options:{...b,parent:"string"==typeof b.parent?b.parent:null==(c=b.parent)?void 0:c.label,label:a}}).then(async()=>this.emit("tauri://created")).catch(async a=>this.emit("tauri://error",a))}static async getByLabel(a){var b;let c=null!=(b=(await l()).find(b=>b.label===a))?b:null;return c?new m(c.label,{skip:!0}):null}static getCurrent(){return new m(h().label,{skip:!0})}static async getAll(){return l()}async listen(a,b){return this._handleTauriEvent(a,b)?()=>{let c=this.listeners[a];c.splice(c.indexOf(b),1)}:(0,e.listen)(a,b,{target:{kind:"WebviewWindow",label:this.label}})}async once(a,b){return this._handleTauriEvent(a,b)?()=>{let c=this.listeners[a];c.splice(c.indexOf(b),1)}:(0,e.once)(a,b,{target:{kind:"WebviewWindow",label:this.label}})}async setBackgroundColor(a){return(0,f.invoke)("plugin:window|set_background_color",{color:a}).then(()=>(0,f.invoke)("plugin:webview|set_webview_background_color",{color:a}))}}b=m,(Array.isArray(c=[g.Window,k])?c:[c]).forEach(a=>{Object.getOwnPropertyNames(a.prototype).forEach(c=>{var d;"object"==typeof b.prototype&&b.prototype&&c in b.prototype||Object.defineProperty(b.prototype,c,null!=(d=Object.getOwnPropertyDescriptor(a.prototype,c))?d:Object.create(null))})}),a.s(["WebviewWindow",0,m],75576)}];

//# sourceMappingURL=_0u3_ui0._.js.map