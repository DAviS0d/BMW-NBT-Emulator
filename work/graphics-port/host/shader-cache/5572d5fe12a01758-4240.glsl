precision highp float;

attribute mediump float a_Color;
attribute mediump vec2 a_TextureCoordinate;
attribute mediump vec3 a_Position,a_Normal,a_Tangent,a_Binormal;
uniform highp mat4 MVPMatrix;
uniform mediump mat4 ModelWorld4;
varying mediump vec3 posWorld;
varying mediump vec2 varCoord;
uniform mediump float time;
uniform mediump float param0,param1,param2,param3;
uniform mediump float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;

void main()
{
	gl_Position = MVPMatrix * vec4(a_Position, 1.0);

	mat4 matWorld4 = ModelWorld4;
	matWorld4[3][0] = 0.;
	posWorld = (matWorld4 * vec4(a_Position, 1.0)).xyz;
	
	float texture_w = 96.;
	
	float texture_h = 480.;
	varCoord = vec2(posWorld.x/texture_w, 1. - (posWorld.z/480. + 0.5));  
	varCoord.x += 0.65;
}
