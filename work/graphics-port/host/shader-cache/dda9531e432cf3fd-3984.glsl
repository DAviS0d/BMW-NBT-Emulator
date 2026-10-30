precision highp float;

attribute highp   vec3 a_Position;
attribute mediump float a_VertexColor;
attribute mediump vec3 a_Normal;
attribute mediump vec2 a_TextureCoordinate;
attribute mediump vec2 a_TextureCoordinate1;
attribute mediump vec3 a_Tangent;
attribute mediump vec3 a_Binormal;
uniform highp   mat4 MVPMatrix;
uniform mediump mat3 ModelWorld;
uniform mediump vec3 EyePosModel;
uniform mediump vec3 LightPosModel;
varying mediump vec2 varCoord;
varying mediump vec2 varCoordDisplaced;
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


void main()
{
	highp mat4 modelViewMatrix = MVPMatrix;
 	mediump vec3 temp;
 	temp = a_Position;	
 	mediump float pivot = oparam4;
 	mediump float scaling = oparam5 - 1.;
 	mediump float offset = (51.*scaling) /2.;
 	if( a_Position.z >= pivot )
 	{
 		temp.z += offset*2.;
 	}
 
	temp.z /= oparam5;
 
	gl_Position = modelViewMatrix * vec4(temp, 1.0);
	varCoord = a_TextureCoordinate.st;
 
	varCoordDisplaced = vec2(varCoord.y + oparam1, varCoord.x);
}
