attribute mediump float a_Color;
attribute mediump vec2 a_TextureCoordinate;
attribute mediump vec3 a_Position,a_Normal,a_Tangent,a_Binormal;
uniform highp mat4 MVPMatrix;
uniform mediump mat3 ModelWorld;
uniform mediump mat4 ModelWorld4;
varying mediump vec3 posWorld;
varying mediump vec2 varCoord,mask_coords;
varying mediump float vc,left;
uniform mediump float time;
uniform mediump float param0,param1,param2,param3;
uniform mediump float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;


void main()
{
	varCoord = a_TextureCoordinate.st;
	vc = a_Color;
	left = step(0.2, vc);
	
	gl_Position = MVPMatrix * vec4(a_Position, 1.0);

	mat4 matWorld4 = ModelWorld4;
	matWorld4[3][0] = 0.;
	posWorld = (matWorld4 * vec4(a_Position, 1.0)).xyz;
	float texture_w = 1.;
	mask_coords = vec2(1. - (posWorld.z /480. + 0.5), posWorld.x/texture_w + 0.5); 
}
