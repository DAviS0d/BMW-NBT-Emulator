precision highp float;

attribute mediump float a_Color;
attribute mediump vec2 a_TextureCoordinate,a_TextureCoordinate1;
attribute mediump vec3 a_Position,a_Normal,a_Tangent,a_Binormal;
uniform highp mat4 MVPMatrix;
uniform mediump mat4 ModelWorld4;
varying mediump vec3 posWorld;
varying mediump vec2 archCoord,varCoord,varCoord1;
varying mediump float sample_width,radius;
uniform mediump float time;
uniform mediump float param0,param1,param2,param3;
uniform mediump float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;

void main()
{
	gl_Position = MVPMatrix * vec4(a_Position, 1.0);
	varCoord = a_TextureCoordinate.st;
	varCoord1 = a_TextureCoordinate1.st;

	/* arch equations */
	mat4 matWorld4 = ModelWorld4;
	matWorld4[3][0] = 0.;
	posWorld = (matWorld4 * vec4(a_Position, 1.0)).xyz;
	archCoord = posWorld.xz + vec2(1309., 28.); 
	sample_width = 128.;
	radius = 1363.;
}























/*

precision highp float;

attribute mediump float a_Color;
attribute mediump vec2 a_TextureCoordinate,a_TextureCoordinate1;
attribute mediump vec3 a_Position,a_Normal,a_Tangent,a_Binormal;
uniform highp mat4 MVPMatrix;
uniform mediump mat4 ModelWorld4;
varying mediump vec3 posWorld;
varying mediump vec2 archCoord,varCoord;
varying mediump float sample_width,radius;
uniform mediump float time;
uniform mediump float param0,param1,param2,param3;
uniform mediump float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;

void main()
{
	gl_Position = MVPMatrix * vec4(a_Position, 1.0);
	varCoord = a_TextureCoordinate.st;

	mat4 matWorld4 = ModelWorld4;
	matWorld4[3][0] = 0.;
	posWorld = (matWorld4 * vec4(a_Position, 1.0)).xyz;
	archCoord = posWorld.xz + vec2(oparam3, 28.);
	sample_width = 5.;
	radius = 1280.;
}
*/