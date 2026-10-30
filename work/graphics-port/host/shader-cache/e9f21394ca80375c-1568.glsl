precision mediump float;

uniform sampler2D tex0;
uniform sampler2D tex1;
uniform sampler2D tex2;
uniform sampler2D tex3;
varying vec3 ReflectDir;
varying vec2 varCoord;
varying vec2 varCoord1;
uniform float time;
uniform float param0;
uniform float param1;
uniform float param2;
uniform float param3;
uniform float oparam0;
uniform float oparam1;
uniform float oparam2;
uniform float oparam3;
uniform float oparam4;

void main(){
 vec4 glow_color = vec4(0.6,0.2,0.0,1.0);
 vec4 pointer_tex = texture2D(tex0, varCoord.xy);
 vec4 p_mask = varCoord1.xxxx;						
 pointer_tex = mix(glow_color, pointer_tex, varCoord1.x);

 vec4 glow_mask = texture2D(tex1, varCoord.xy);
 gl_FragColor = vec4(pointer_tex.rgb, (glow_mask.a+p_mask.a));
 gl_FragColor.a *= oparam0; 						
 
}