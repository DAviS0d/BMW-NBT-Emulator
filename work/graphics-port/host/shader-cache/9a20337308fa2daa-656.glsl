precision mediump float;

uniform sampler2D tex0;
varying mediump vec2 varCoord;
uniform float oparam0;

void main(){
	
	vec4 sample = texture2D(tex0,varCoord);
	gl_FragColor = sample * oparam0; 
}