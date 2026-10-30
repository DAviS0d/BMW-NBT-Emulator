precision mediump float;

uniform sampler2D tex0;
uniform sampler2D tex1;
uniform sampler2D tex2;
uniform sampler2D tex3;
varying mediump vec2 varCoord;
uniform mediump float time;
uniform mediump float param0;
uniform mediump float param1;
uniform mediump float param2;
uniform mediump float param3;
uniform mediump float oparam0;
uniform mediump float oparam1;
uniform mediump float oparam2;
uniform mediump float oparam3; // X
uniform mediump float oparam4; // Y
uniform mediump float oparam5; // Radius
uniform mediump float oparam6; // Xwidth
uniform mediump float oparam7; // XOffset

void main()
{
	gl_FragColor = texture2D( tex0, varCoord.xy ); 
}