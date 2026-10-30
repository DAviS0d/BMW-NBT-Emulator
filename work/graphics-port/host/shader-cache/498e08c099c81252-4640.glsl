precision highp float;

attribute mediump float a_Color;
attribute mediump vec2 a_TextureCoordinate;
attribute mediump vec3 a_Position,a_Normal,a_Tangent,a_Binormal;
uniform highp mat4 MVPMatrix;
uniform mediump mat4 ModelWorld4;
varying mediump vec3 posWorld;
varying mediump vec3 co_btm,co_tp;
varying mediump vec2 varCoord,archCoord;
varying mediump float sample_width,radius;
uniform mediump float time;
uniform mediump float param0,param1,param2,param3;
uniform mediump float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;

void main()
{
	gl_Position = MVPMatrix * vec4(a_Position, 1.0);

	varCoord = a_TextureCoordinate.st;
	varCoord.y *= 0.25;
	varCoord.y += oparam1;
	
	float active_add = oparam2 * 0.3;  // add 0.3 when active
	co_btm = vec3(0.19, 0.31, 0.31) + active_add;
	co_tp = vec3(0.35, 0.45, 0.45) + active_add;

	/* arch equations */
	mat4 matWorld4 = ModelWorld4;
	matWorld4[3][0] = 0.;
	posWorld = (matWorld4 * vec4(a_Position, 1.0)).xyz;
	archCoord = posWorld.xz + vec2(1312., 28.);
	sample_width = -10.;//-2.;
	radius = 1283.;
}
