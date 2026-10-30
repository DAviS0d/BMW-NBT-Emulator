precision mediump float;

uniform sampler2D tex0;
uniform sampler2D tex1;
uniform sampler2D tex2;
uniform sampler2D tex3;
varying vec3 ReflectDir;
varying vec2 varCoord;
uniform float time;
uniform float param0;
uniform float param1;
uniform float param2;
uniform float param3;
uniform float oparam0;
uniform float oparam1;
uniform float oparam2;
uniform float oparam3;

void main()
{
 vec4 base = texture2D(tex0,varCoord.yx );
 vec4 reflection = texture2D(tex1,ReflectDir.xy);
 
 gl_FragColor = oparam0 * vec4( base.rgb + reflection.rgb, base.a );
}