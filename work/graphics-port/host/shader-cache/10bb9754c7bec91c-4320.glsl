precision highp float;

attribute mediump float a_Color;
attribute mediump vec2 a_TextureCoordinate,a_TextureCoordinate1;
attribute mediump vec3 a_Position,a_Normal,a_Tangent,a_Binormal;
uniform highp mat4 MVPMatrix;
uniform mediump mat3 ModelWorld;
uniform mediump vec3 EyePosModel;
uniform mediump vec3 LightPosModel;
varying mediump vec2 varCoord;
varying mediump float selected_rings;
varying mediump float history_on;
varying mediump float vc;
uniform mediump float time;
uniform mediump float param0,param1,param2,param3;
uniform mediump float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;

#define is_zero(A) (1.-abs(sign(A)))
#define is_equal(A,B) ((abs(A-B))<0.02?1.0:0.0)

void main()
{
	gl_Position = MVPMatrix * vec4(a_Position, 1.0);
	varCoord = a_TextureCoordinate.st;
	vc = a_Color;

	selected_rings = 0.;
	selected_rings += is_equal(varCoord.x, 0.0) * oparam1;
	selected_rings += is_equal(varCoord.x, 0.1) * oparam2;
	selected_rings += is_equal(varCoord.x, 0.2) * oparam3;
	selected_rings += is_equal(varCoord.x, 0.3) * oparam4;
	selected_rings += is_equal(varCoord.x, 0.4) * oparam5;
	selected_rings += is_equal(varCoord.x, 0.5) * oparam6;
	selected_rings += is_equal(varCoord.x, 0.6) * oparam7;
	
	history_on = step(1.2, selected_rings);                          
}
