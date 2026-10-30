precision highp float;

attribute         vec3 a_Position;
attribute mediump float a_VertexColor;
attribute mediump vec3 a_Normal;
attribute mediump vec2 a_TextureCoordinate;
attribute mediump vec2 a_TextureCoordinate1;
attribute mediump vec3 a_Tangent;
attribute mediump vec3 a_Binormal;

uniform         mat4 MVPMatrix;
uniform mediump mat3 ModelWorld;
uniform mediump vec3 EyePosModel;
uniform mediump vec3 LightPosModel;
uniform mediump float time;
uniform mediump float param0;
uniform mediump float param1;
uniform mediump float param2;
uniform mediump float param3;
uniform mediump float oparam0;
uniform mediump float oparam1;
uniform mediump float oparam2;
uniform mediump float oparam3;
uniform mediump float oparam4;
uniform mediump float oparam5;
uniform mediump float oparam6;
uniform mediump float oparam7;

varying mediump vec2 varCoord;
varying mediump vec4 varCoord1;
varying mediump vec4 varCoord2;
varying mediump vec4 varCoord3;
varying mediump vec4 varCoord4;

void main()
{
	gl_Position = MVPMatrix * vec4(a_Position, 1.0);
 
	float start_x = oparam4;
	float start_y = oparam5;
	float stretch_factor_x = oparam6;
	float stretch_factor_y = oparam7;
 
	varCoord = vec2( start_x + a_TextureCoordinate.s * stretch_factor_x, 
 		 			 start_y + a_TextureCoordinate.t * stretch_factor_y );
 
	float step_x = 1. / 1280.;
	float step_y = 1. / 480.;
 
	vec2 coordP = varCoord + vec2( 2.5*step_x, 2.5*step_y );
	vec2 coordN = varCoord + vec2( -2.5*step_x, -2.5*step_y );
	vec2 coordDiagP = varCoord + vec2( 1.25*step_x, 1.25*step_y );
	vec2 coordDiagN = varCoord + vec2( -1.25*step_x, -1.25*step_y );
 
	varCoord1.xy = vec2( coordP.x, varCoord.y );
	varCoord1.zw = vec2( varCoord.x, coordP.y );
	varCoord2.xy = vec2( coordN.x, varCoord.y );
	varCoord2.zw = vec2( varCoord.x, coordN.y );
	varCoord3.xy = vec2( coordDiagP.x, coordDiagP.y );
	varCoord3.zw = vec2( coordDiagN.x, coordDiagN.y );
	varCoord4.xy = vec2( coordDiagN.x, coordDiagP.y );
	varCoord4.zw = vec2( coordDiagP.x, coordDiagN.y );
}