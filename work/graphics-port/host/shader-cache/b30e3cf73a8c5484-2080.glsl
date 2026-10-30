precision highp float;

attribute mediump vec2 a_TextureCoordinate;
attribute mediump vec3 a_Position;
uniform highp mat4 MVPMatrix;
varying mediump vec2 varCoord;
uniform mediump float oparam4;  //rotate

vec3 rotate_like_clock(vec3 point, float angle){
	vec3 r;
	r.x = point.x * cos(angle) + point.z * sin(angle);
	r.y = point.y;
	r.z = point.z * cos(angle) - point.x * sin(angle);
	return r;
}

void main(){
	
	varCoord = a_TextureCoordinate.st;
	gl_Position = MVPMatrix * vec4(rotate_like_clock(a_Position,oparam4), 1.0);
}
