precision highp float;

attribute      vec3 a_Position;
attribute mediump float a_VertexColor;
attribute mediump vec3 a_Normal;
attribute mediump vec2 a_TextureCoordinate;
attribute mediump vec2 a_TextureCoordinate1;
attribute mediump vec3 a_Tangent;
attribute mediump vec3 a_Binormal;
uniform       mat4 MVPMatrix;
uniform mediump mat3 ModelWorld;
uniform mediump vec3 EyePosModel;
uniform mediump vec3 LightPosModel;
varying mediump vec2 varCoord;
varying mediump vec2 varCoord2;
varying mediump vec2 varCoord3;
varying mediump vec2 varCoord4;
varying mediump vec2 varCoord5;
varying mediump vec2 varCoord6;
uniform mediump float time;
uniform mediump float param0,param1,param2,param3;
uniform mediump float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;

void main()
{
	gl_Position = MVPMatrix * vec4(a_Position+vec3(1,0,0)*oparam3, 1.0);

	varCoord = a_TextureCoordinate.st;
	
	varCoord2 = a_TextureCoordinate1.st;
	varCoord2 *= vec2( oparam6, oparam7 );
	varCoord2 += vec2( oparam4, oparam5 );
	
	varCoord3 = varCoord2 + vec2( -0.003,  0.000 );
	varCoord4 = varCoord2 + vec2(  0.000, -0.003 );
	varCoord5 = varCoord2 + vec2(  0.003,  0.000 );
	varCoord6 = varCoord2 + vec2(  0.000,  0.003 );
}
